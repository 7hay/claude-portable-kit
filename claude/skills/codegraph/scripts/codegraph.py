#!/usr/bin/env python3
"""
codegraph.py — Code Knowledge Graph builder (Python / JS / TS / Rust)

動画 Jack Roberts「Claude Code + Graphify」のコード版。任意のコードベースを解析し、
import 依存グラフを構築して `CODEMAP.md` に出力する。Claude Code は全ソースを読み直す
代わりにこの地図を読むことで、トークン消費を抑えつつ全体像を掴める。

設計方針:
  - 追加依存ゼロ（Python 標準ライブラリのみ）。どのプロジェクトでも即実行可能。
  - Python は `ast` で精読（正規表現より正確で誤検出が少ない）。JS/TS/Rust は import 構文を
    正規表現で抽出（各言語に標準パーサが無いため）。
  - ノート版ナレッジグラフ（Graphify）と同じ5段パイプライン構造。

対応する動画の概念:
  - 精読            → extract_module_info（import/関数/クラス/docstring 抽出）
  - God Nodes       → find_god_nodes（被import数 = 壊すと影響大の根幹ファイル）
  - Blast Radius    → blast_radius（変更が波及する全モジュールを逆方向に辿る）
  - クラスタリング  → detect_clusters（貪欲モジュラリティによるコミュニティ検出）
  - Facts/Guesses   → 内部解決 import = Fact / 外部ライブラリ = External / 解決不能 = Guess

Usage:
    python tools/codegraph.py --src PATH [--out PATH]

Exit codes: 0 = success, 1 = error
"""

from __future__ import annotations

import argparse
import ast
import os
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

# ──────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────

EXCLUDE_DIRS = {
    "__pycache__", ".git", "node_modules", "target", "build", "dist",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", "site-packages", ".tox",
    ".eggs", ".idea", ".vscode", "vendor",
}

LANG_BY_SUFFIX = {
    ".py": "python",
    ".js": "js", ".jsx": "js", ".mjs": "js", ".cjs": "js",
    ".ts": "ts", ".tsx": "ts",
    ".rs": "rust",
}
JS_LANGS = {"js", "ts"}
JS_EXTS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")
SUPPORTED_SUFFIXES = set(LANG_BY_SUFFIX)


def _lang_of(path: Path) -> str | None:
    return LANG_BY_SUFFIX.get(path.suffix)


# ──────────────────────────────────────────────
# Graph (stdlib-only, networkx 非依存)
# ──────────────────────────────────────────────

class CodeGraph:
    """A tiny directed graph. Nodes are module ids; edges are imports."""

    def __init__(self) -> None:
        self._nodes: dict[str, dict] = {}
        self._out: dict[str, dict[str, str]] = defaultdict(dict)  # src -> {dst: kind}
        self._in: dict[str, set[str]] = defaultdict(set)          # dst -> {src}

    def add_node(self, name: str, **attrs: Any) -> None:
        self._nodes.setdefault(name, {})
        if attrs:
            self._nodes[name].update(attrs)

    def add_edge(self, src: str, dst: str, kind: str = "internal") -> None:
        if dst not in self._nodes:
            self.add_node(dst)
        if dst not in self._out[src]:
            self._out[src][dst] = kind
            self._in[dst].add(src)

    def nodes(self) -> list[str]:
        return list(self._nodes)

    def has_node(self, name: str) -> bool:
        return name in self._nodes

    def node_attr(self, name: str) -> dict:
        return self._nodes[name]

    def successors(self, name: str) -> set[str]:
        return set(self._out.get(name, {}))

    def predecessors(self, name: str) -> set[str]:
        return set(self._in.get(name, set()))

    def in_degree(self, name: str) -> int:
        return len(self._in.get(name, set()))

    def out_degree(self, name: str) -> int:
        return len(self._out.get(name, {}))

    def edge_kind(self, src: str, dst: str) -> str | None:
        return self._out.get(src, {}).get(dst)


# ──────────────────────────────────────────────
# 1. scan_code
# ──────────────────────────────────────────────

def scan_code(root: Path, suffixes: set[str] | None = None) -> list[Path]:
    """Recursively collect source files, skipping vendored/build/venv directories."""
    wanted = suffixes or SUPPORTED_SUFFIXES
    results: list[Path] = []
    for path in root.rglob("*"):
        if path.suffix not in wanted or not path.is_file():
            continue
        if any(
            part in EXCLUDE_DIRS or part == "venv" or part.startswith(".venv")
            for part in path.parts
        ):
            continue
        results.append(path)
    return sorted(results)


# ──────────────────────────────────────────────
# 2. module_name (language-aware id)
# ──────────────────────────────────────────────

def module_name(path: Path, root: Path) -> str:
    """Return the module id of *path* relative to *root*.

    Python uses dotted names (pkg.mod); other languages use the posix path
    without extension (src/a), matching how their imports reference files.
    """
    rel = path.relative_to(root)
    if _lang_of(path) == "python":
        parts = list(rel.with_suffix("").parts)
        if parts and parts[-1] == "__init__":
            parts = parts[:-1]
        return ".".join(parts)
    return rel.with_suffix("").as_posix()


# ──────────────────────────────────────────────
# 3. extract_module_info (language dispatch)
# ──────────────────────────────────────────────

def extract_module_info(path: Path) -> dict[str, Any]:
    """Parse one source file and return structured metadata.

    Common keys: lang, docstring, functions, classes, imports, loc, path,
    parse_error. The shape of each `imports` item is language-specific and
    interpreted by build_graph.
    """
    lang = _lang_of(path) or "python"
    src = path.read_text(encoding="utf-8", errors="replace")
    loc = len(src.splitlines())
    base = {"lang": lang, "loc": loc, "path": path, "parse_error": False,
            "docstring": "", "functions": [], "classes": [], "imports": []}

    if lang == "python":
        base.update(_extract_python(src))
    elif lang in JS_LANGS:
        base.update(_extract_js(src))
    elif lang == "rust":
        base.update(_extract_rust(src))
    return base


def _extract_python(src: str) -> dict[str, Any]:
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return {"parse_error": True}

    functions: list[str] = []
    classes: list[str] = []
    for node in tree.body:  # top-level definitions only
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(node.name)
        elif isinstance(node, ast.ClassDef):
            classes.append(node.name)

    imports: list[dict] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append({"kind": "import", "module": alias.name, "level": 0})
        elif isinstance(node, ast.ImportFrom):
            imports.append({
                "kind": "from", "module": node.module, "level": node.level or 0,
                "names": [a.name for a in node.names],
            })
    return {"docstring": (ast.get_docstring(tree) or "").strip(),
            "functions": functions, "classes": classes, "imports": imports}


_RE_JS_FROM = re.compile(r"""(?:import|export)\b[^;'"]*?\bfrom\s*['"]([^'"]+)['"]""")
_RE_JS_BARE = re.compile(r"""\bimport\s*['"]([^'"]+)['"]""")
_RE_JS_REQUIRE = re.compile(r"""\b(?:require|import)\(\s*['"]([^'"]+)['"]\s*\)""")
_RE_JS_FUNC = re.compile(r"""\b(?:export\s+)?(?:default\s+)?function\s+(\w+)""")
_RE_JS_CONST_FN = re.compile(r"""\bexport\s+const\s+(\w+)\s*=\s*(?:async\s*)?\(""")
_RE_JS_CLASS = re.compile(r"""\b(?:export\s+)?(?:default\s+)?class\s+(\w+)""")


def _extract_js(src: str) -> dict[str, Any]:
    specs: list[str] = []
    for pat in (_RE_JS_FROM, _RE_JS_BARE, _RE_JS_REQUIRE):
        specs += pat.findall(src)
    imports = [{"spec": s} for s in dict.fromkeys(specs)]  # dedupe, keep order
    functions = list(dict.fromkeys(_RE_JS_FUNC.findall(src) + _RE_JS_CONST_FN.findall(src)))
    classes = list(dict.fromkeys(_RE_JS_CLASS.findall(src)))
    return {"functions": functions, "classes": classes, "imports": imports}


_RE_RS_MOD = re.compile(r"""^\s*(?:pub\s+)?mod\s+(\w+)\s*;""", re.MULTILINE)
_RE_RS_USE = re.compile(r"""^\s*(?:pub\s+)?use\s+([\w:]+)""", re.MULTILINE)
_RE_RS_FN = re.compile(r"""\b(?:pub\s+)?(?:async\s+)?fn\s+(\w+)""")
_RE_RS_TYPE = re.compile(r"""\b(?:pub\s+)?(?:struct|enum|trait)\s+(\w+)""")


def _extract_rust(src: str) -> dict[str, Any]:
    imports: list[dict] = []
    for name in _RE_RS_MOD.findall(src):
        imports.append({"kind": "mod", "name": name})
    for path in _RE_RS_USE.findall(src):
        imports.append({"kind": "use", "path": path})
    functions = list(dict.fromkeys(_RE_RS_FN.findall(src)))
    classes = list(dict.fromkeys(_RE_RS_TYPE.findall(src)))
    return {"functions": functions, "classes": classes, "imports": imports}


# ──────────────────────────────────────────────
# 4. build_graph
# ──────────────────────────────────────────────

def build_graph(files: list[Path], root: Path) -> CodeGraph:
    """Build an import-dependency graph from *files* rooted at *root*."""
    g = CodeGraph()

    infos: dict[str, dict] = {}
    path_of: dict[str, Path] = {}
    is_pkg: dict[str, bool] = {}
    for f in files:
        name = module_name(f, root)
        info = extract_module_info(f)
        infos[name] = info
        path_of[name] = f
        is_pkg[name] = (f.name == "__init__.py")
        g.add_node(
            name, lang=info["lang"], docstring=info["docstring"],
            functions=info["functions"], classes=info["classes"],
            loc=info["loc"], path=str(f), external_imports=[], unresolved=[],
        )

    internal = set(g.nodes())

    for name, info in infos.items():
        attr = g.node_attr(name)
        lang = info["lang"]
        for imp in info["imports"]:
            if lang == "python":
                _wire_python(g, attr, name, imp, is_pkg.get(name, False), internal)
            elif lang in JS_LANGS:
                _wire_js(g, attr, name, imp, path_of[name], root, internal)
            elif lang == "rust":
                _wire_rust(g, attr, name, imp, path_of[name], root, internal)
    return g


def _append_unique(seq: list, value: str) -> None:
    if value and value not in seq:
        seq.append(value)


# ── Python wiring ──────────────────────────────

def _wire_python(g, attr, name, imp, current_is_pkg, internal) -> None:
    resolved, guess = _resolve_py_imports(imp, name, current_is_pkg, internal)
    if resolved:
        for target in resolved:
            if target != name:
                g.add_edge(name, target, kind="internal")  # Fact
    elif guess:
        _append_unique(attr["unresolved"], _py_imp_label(imp))  # Guess
    else:
        ext = (imp.get("module") or "").split(".")[0]
        if ext:
            _append_unique(attr["external_imports"], ext)  # External


def _py_imp_label(imp: dict) -> str:
    if imp["kind"] == "import":
        return imp["module"]
    dots = "." * imp.get("level", 0)
    return f"{dots}{imp['module'] or ''}".rstrip(".") or dots


def _longest_internal_prefix(dotted: str, internal: set[str]) -> str | None:
    parts = dotted.split(".")
    for i in range(len(parts), 0, -1):
        cand = ".".join(parts[:i])
        if cand in internal:
            return cand
    return None


def _relative_base(current: str, is_pkg: bool, level: int) -> str | None:
    parts = current.split(".") if current else []
    package_parts = parts if is_pkg else parts[:-1]
    up = level - 1
    if up > len(package_parts):
        return None
    return ".".join(package_parts[: len(package_parts) - up])


def _resolve_py_imports(imp, current, current_is_pkg, internal) -> tuple[set[str], bool]:
    """Resolve a Python import to internal modules. Submodules win over packages,
    so `from pkg import utils` links to `pkg.utils`, not `pkg`. is_guess is True
    only for relative imports that cannot be resolved."""
    resolved: set[str] = set()
    if imp["kind"] == "import":
        cand = _longest_internal_prefix(imp["module"], internal)
        if cand:
            resolved.add(cand)
        return (resolved, False)

    level = imp.get("level", 0)
    if level == 0:
        mod = imp["module"] or ""
        for n in imp["names"]:
            cand = f"{mod}.{n}" if mod else n
            if cand in internal:
                resolved.add(cand)
        if resolved:
            return (resolved, False)
        if mod in internal:
            return ({mod}, False)
        cand = _longest_internal_prefix(mod, internal)
        if cand:
            resolved.add(cand)
        return (resolved, False)

    base = _relative_base(current, current_is_pkg, level)
    if base is None:
        return (set(), True)
    mod = imp["module"]
    if mod:
        full = f"{base}.{mod}" if base else mod
        for n in imp["names"]:
            cand = f"{full}.{n}"
            if cand in internal:
                resolved.add(cand)
        if resolved:
            return (resolved, False)
        if full in internal:
            return ({full}, False)
        cand = _longest_internal_prefix(full, internal)
        if cand:
            return ({cand}, False)
        return (set(), True)
    for n in imp["names"]:
        cand = f"{base}.{n}" if base else n
        if cand in internal:
            resolved.add(cand)
    return (resolved, not resolved)


# ── JS/TS wiring ───────────────────────────────

def _wire_js(g, attr, name, imp, current_path, root, internal) -> None:
    spec = imp["spec"]
    if spec.startswith("."):
        target = _resolve_js(spec, current_path, root, internal)
        if target and target != name:
            g.add_edge(name, target, kind="internal")  # Fact
        else:
            _append_unique(attr["unresolved"], spec)    # Guess (relative, unresolved)
    else:
        ext = spec.split("/")[0]
        if ext.startswith("@"):  # scoped package @scope/name
            ext = "/".join(spec.split("/")[:2])
        if ext:
            _append_unique(attr["external_imports"], ext)  # External


def _resolve_js(spec, current_path: Path, root: Path, internal: set[str]) -> str | None:
    target = os.path.normpath(os.path.join(str(current_path.parent), spec))
    try:
        rel = Path(target).relative_to(root).as_posix()
    except ValueError:
        return None
    for ext in JS_EXTS:
        if rel.endswith(ext):
            rel = rel[: -len(ext)]
            break
    for cand in (rel, f"{rel}/index"):
        if cand in internal:
            return cand
    return None


# ── Rust wiring ────────────────────────────────

def _wire_rust(g, attr, name, imp, current_path, root, internal) -> None:
    if imp["kind"] == "mod":
        # `mod foo;` → sibling file foo.rs or foo/mod.rs in the same directory
        rel_dir = current_path.parent.relative_to(root).as_posix()
        prefix = f"{rel_dir}/" if rel_dir != "." else ""
        for cand in (f"{prefix}{imp['name']}", f"{prefix}{imp['name']}/mod"):
            if cand in internal:
                g.add_edge(name, cand, kind="internal")  # Fact
                return
        return
    # `use` — record external crates only (crate/self/super are intra-crate paths
    # whose file mapping needs the full mod tree; resolved via `mod` edges instead).
    head = imp["path"].split("::")[0]
    if head and head not in {"crate", "self", "super"}:
        _append_unique(attr["external_imports"], head)  # External


# ──────────────────────────────────────────────
# 5. find_god_nodes / blast_radius / detect_clusters
# ──────────────────────────────────────────────

def find_god_nodes(g: CodeGraph, top_n: int = 10) -> list[tuple[str, int]]:
    """Rank nodes by in-degree (= how many modules import them). 被import数が多い
    ほど壊したときの影響が大きい＝プロジェクトの根幹。"""
    scored = [(n, g.in_degree(n)) for n in g.nodes()]
    scored.sort(key=lambda x: (-x[1], -g.out_degree(x[0]), x[0]))
    return scored[:top_n]


def blast_radius(g: CodeGraph, node: str) -> set[str]:
    """All modules that (transitively) import *node* — the impact range of a change."""
    seen: set[str] = set()
    stack = list(g.predecessors(node))
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        stack.extend(g.predecessors(cur))
    seen.discard(node)
    return seen


def detect_clusters(g: CodeGraph) -> list[set[str]]:
    """Community detection via greedy modularity maximisation (Clauset-Newman-Moore)
    on the undirected projection. Splits loosely-coupled groups that a plain
    connected-components pass would lump together."""
    nodes = g.nodes()
    deg: dict[str, int] = {n: 0 for n in nodes}
    edges: set[tuple[str, str]] = set()
    for s in nodes:
        for d in g.successors(s):
            if s == d:
                continue
            key = (s, d) if s < d else (d, s)
            if key not in edges:
                edges.add(key)
                deg[s] += 1
                deg[d] += 1
    m = len(edges)
    if m == 0:
        return _sorted_clusters([{n} for n in nodes])

    members: dict[str, set[str]] = {n: {n} for n in nodes}
    d_comm: dict[str, int] = dict(deg)
    between: dict[str, dict[str, int]] = {n: defaultdict(int) for n in nodes}
    for a, b in edges:
        between[a][b] += 1
        between[b][a] += 1

    while True:
        best_pair = None
        best_dq = 1e-12  # require a strictly positive gain
        for a in between:
            for b, cnt in between[a].items():
                if a >= b:
                    continue
                dq = cnt / m - (d_comm[a] * d_comm[b]) / (2 * m * m)
                if dq > best_dq:
                    best_dq = dq
                    best_pair = (a, b)
        if best_pair is None:
            break
        a, b = best_pair
        members[a] |= members[b]
        d_comm[a] += d_comm[b]
        for c, cnt in between[b].items():
            if c == a:
                continue
            between[a][c] += cnt
            between[c][a] += cnt
            between[c].pop(b, None)
        between[a].pop(b, None)
        del between[b], members[b], d_comm[b]

    return _sorted_clusters(list(members.values()))


def _sorted_clusters(clusters: list[set[str]]) -> list[set[str]]:
    return sorted(clusters, key=lambda c: (-len(c), sorted(c)[0]))


# ──────────────────────────────────────────────
# 6. generate_output
# ──────────────────────────────────────────────

def generate_output(g: CodeGraph, out_dir: Path, root: Path) -> None:
    """Write CODEMAP.md to out_dir. Never modifies anything outside out_dir."""
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "CODEMAP.md").write_text(render_codemap(g, root), encoding="utf-8")


def render_codemap(g: CodeGraph, root: Path) -> str:
    """Render the CODEMAP.md body as a string (used by both file output and the
    registry's token-savings estimate)."""
    total_nodes = len(g.nodes())
    internal_edges = sum(g.out_degree(n) for n in g.nodes())
    external = sorted({e for n in g.nodes() for e in g.node_attr(n)["external_imports"]})
    guesses = [(n, g.node_attr(n)["unresolved"]) for n in g.nodes()
               if g.node_attr(n)["unresolved"]]
    lang_counts: dict[str, int] = defaultdict(int)
    for n in g.nodes():
        lang_counts[g.node_attr(n).get("lang", "?")] += 1
    lang_str = ", ".join(f"{k}:{v}" for k, v in sorted(lang_counts.items()))
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        "# Code Knowledge Graph — CODEMAP",
        "",
        f"**Source root**: `{root}`  ",
        f"**Generated**: {generated_at}  ",
        f"**Modules (nodes)**: {total_nodes}  ",
        f"**Languages**: {lang_str}  ",
        f"**Internal imports (Fact edges)**: {internal_edges}  ",
        f"**External dependencies**: {len(external)}  ",
        "",
        "## God Nodes（被import数・上位10＝根幹ファイル）",
        "",
        "| Rank | Module | In | Out | Blast Radius |",
        "|------|--------|----|-----|--------------|",
    ]
    for rank, (node, indeg) in enumerate(find_god_nodes(g, top_n=10), 1):
        lines.append(
            f"| {rank} | `{node}` | {indeg} | {g.out_degree(node)} "
            f"| {len(blast_radius(g, node))} |"
        )

    clusters = detect_clusters(g)
    lines += ["", "## クラスタ（モジュラリティ・コミュニティ）", ""]
    for i, comp in enumerate(clusters, 1):
        if len(comp) == 1:
            continue
        members = ", ".join(f"`{m}`" for m in sorted(comp))
        lines.append(f"- **Cluster {i}** ({len(comp)}): {members}")
    singletons = [next(iter(c)) for c in clusters if len(c) == 1]
    if singletons:
        lines.append(f"- **孤立モジュール** ({len(singletons)}): "
                     + ", ".join(f"`{m}`" for m in sorted(singletons)))

    if external:
        lines += ["", "## 外部依存（External）", "", ", ".join(f"`{e}`" for e in external)]

    if guesses:
        lines += ["", "## 未解決 import（Guess・要確認）", ""]
        for node, items in guesses:
            lines.append(f"- `{node}`: " + ", ".join(f"`{x}`" for x in items))

    lines += ["", "## モジュール別サマリー", ""]
    for node in sorted(g.nodes()):
        attr = g.node_attr(node)
        if not attr.get("path"):
            continue
        summary = (attr["docstring"].splitlines()[0] if attr["docstring"] else "")
        radius = blast_radius(g, node)
        lines.append(f"### `{node}`")
        if summary:
            lines.append(f"*{summary}*")
        lines.append("")
        if attr["classes"]:
            lines.append("- **Types/Classes**: " + ", ".join(attr["classes"][:15]))
        if attr["functions"]:
            lines.append("- **Functions**: " + ", ".join(attr["functions"][:15]))
        deps = sorted(g.successors(node))
        if deps:
            lines.append("- **Imports (Fact)**: " + ", ".join(f"`{d}`" for d in deps))
        if attr["external_imports"]:
            lines.append("- **External**: "
                         + ", ".join(f"`{e}`" for e in sorted(attr["external_imports"])[:15]))
        lines.append(f"- **Blast Radius**: {len(radius)} module(s)"
                     + (f" — {', '.join(sorted(radius)[:10])}" if radius else ""))
        lines.append(f"- **LOC**: {attr['loc']}")
        lines.append("")

    lines.append("> Auto-generated by `tools/codegraph.py`. Do NOT edit manually.")
    return "\n".join(lines)


# ──────────────────────────────────────────────
# CLI entrypoint
# ──────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    import time

    parser = argparse.ArgumentParser(description="Build a code knowledge graph")
    parser.add_argument("--src", type=Path, required=True, help="source root to scan")
    parser.add_argument("--out", type=Path, default=None,
                        help="output dir for CODEMAP.md (default: <src>/.codegraph)")
    args = parser.parse_args(argv)

    src: Path = args.src.resolve()
    if not src.is_dir():
        print(f"[codegraph] ERROR: not a directory: {src}", file=sys.stderr)
        return 1
    out_dir: Path = (args.out or (src / ".codegraph")).resolve()

    t0 = time.time()
    print(f"[codegraph] Scanning: {src}", flush=True)
    files = scan_code(src)
    print(f"[codegraph] Found {len(files)} source files", flush=True)

    g = build_graph(files, src)
    print(f"[codegraph] Graph: {len(g.nodes())} modules, "
          f"{sum(g.out_degree(n) for n in g.nodes())} internal edges", flush=True)

    generate_output(g, out_dir, src)
    print(f"[codegraph] Wrote {out_dir / 'CODEMAP.md'} in {time.time() - t0:.2f}s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
