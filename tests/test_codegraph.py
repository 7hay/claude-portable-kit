"""
Tests for codegraph.py
Run: python3 -m pytest tests/test_codegraph.py -v

設計意図: 動画 Graphify の「コード版」。Python の import/定義を ast で精読し、
依存グラフ・God Nodes・Blast Radius・クラスタ・Facts/Guesses を検証する。
"""

import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "claude" / "skills" / "codegraph" / "scripts"))
import codegraph


# ──────────────────────────────────────────────
# Fixture: a minimal synthetic Python package
#   pkg.utils  ← imported by core, api  (in-degree 2 → God Node)
#   pkg.core   ← imported by api        (imports utils)
#   pkg.api    → imports core, utils    (uses relative + absolute imports)
#   pkg.lonely → no internal deps       (separate cluster)
# ──────────────────────────────────────────────

def make_pkg(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    pkg = root / "pkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")

    (pkg / "utils.py").write_text(textwrap.dedent('''\
        """Utility helpers."""
        import os

        def helper(x):
            return os.path.join(x, "a")
    '''), encoding="utf-8")

    (pkg / "core.py").write_text(textwrap.dedent('''\
        """Core engine."""
        from pkg import utils

        class Engine:
            def run(self):
                return utils.helper("/tmp")

        def boot():
            return Engine()
    '''), encoding="utf-8")

    (pkg / "api.py").write_text(textwrap.dedent('''\
        """Public API."""
        from pkg.core import Engine
        from . import utils

        def serve():
            return Engine(), utils.helper(".")
    '''), encoding="utf-8")

    (pkg / "lonely.py").write_text(textwrap.dedent('''\
        """Standalone module, no internal deps."""
        def alone():
            return 42
    '''), encoding="utf-8")

    # Directories that must be ignored
    venv = root / ".venv" / "lib"
    venv.mkdir(parents=True)
    (venv / "ignored.py").write_text("x = 1\n", encoding="utf-8")
    cache = pkg / "__pycache__"
    cache.mkdir()
    (cache / "core.cpython-312.pyc").write_text("", encoding="utf-8")
    return root


# ──────────────────────────────────────────────
# 1. scan_code
# ──────────────────────────────────────────────

def test_scan_code_finds_py_excludes_venv_and_cache(tmp_path):
    root = make_pkg(tmp_path)
    files = codegraph.scan_code(root)
    names = {p.name for p in files}
    assert {"__init__.py", "utils.py", "core.py", "api.py", "lonely.py"} <= names
    assert "ignored.py" not in names          # .venv excluded
    assert all(p.suffix == ".py" for p in files)  # no .pyc


# ──────────────────────────────────────────────
# 2. module_name
# ──────────────────────────────────────────────

def test_module_name_dotted(tmp_path):
    root = make_pkg(tmp_path)
    assert codegraph.module_name(root / "pkg" / "core.py", root) == "pkg.core"
    assert codegraph.module_name(root / "pkg" / "__init__.py", root) == "pkg"


# ──────────────────────────────────────────────
# 3. extract_module_info (ast 精読)
# ──────────────────────────────────────────────

def test_extract_module_info(tmp_path):
    root = make_pkg(tmp_path)
    info = codegraph.extract_module_info(root / "pkg" / "core.py")
    assert info["docstring"].startswith("Core engine")
    assert "Engine" in info["classes"]
    assert "boot" in info["functions"]
    assert info["loc"] > 0
    # imports captured (raw, to be resolved by build_graph)
    assert any(imp.get("module") == "pkg" for imp in info["imports"])


def test_extract_handles_syntax_error(tmp_path):
    bad = tmp_path / "bad.py"
    bad.write_text("def broken(:\n", encoding="utf-8")
    info = codegraph.extract_module_info(bad)
    assert info["parse_error"] is True
    assert info["functions"] == []


# ──────────────────────────────────────────────
# 4. build_graph — internal import = Fact, external recorded separately
# ──────────────────────────────────────────────

def test_build_graph_internal_edges_are_facts(tmp_path):
    root = make_pkg(tmp_path)
    g = codegraph.build_graph(codegraph.scan_code(root), root)
    assert "pkg.core" in g.nodes()
    # core -> utils is an internal (Fact) edge
    assert "pkg.utils" in g.successors("pkg.core")
    assert g.edge_kind("pkg.core", "pkg.utils") == "internal"
    # external `import os` is NOT a graph edge; recorded on the node
    assert "os" not in g.successors("pkg.utils")
    assert "os" in g.node_attr("pkg.utils")["external_imports"]


def test_relative_and_absolute_imports_resolved(tmp_path):
    root = make_pkg(tmp_path)
    g = codegraph.build_graph(codegraph.scan_code(root), root)
    # api: `from pkg.core import Engine` (absolute) + `from . import utils` (relative)
    assert "pkg.core" in g.successors("pkg.api")
    assert "pkg.utils" in g.successors("pkg.api")


# ──────────────────────────────────────────────
# 5. find_god_nodes — most-imported first
# ──────────────────────────────────────────────

def test_find_god_nodes_ranks_most_imported_first(tmp_path):
    root = make_pkg(tmp_path)
    g = codegraph.build_graph(codegraph.scan_code(root), root)
    gods = codegraph.find_god_nodes(g, top_n=3)
    assert gods[0][0] == "pkg.utils"   # in-degree 2 = 根幹
    assert gods[0][1] == 2


# ──────────────────────────────────────────────
# 6. blast_radius — transitive reverse impact
# ──────────────────────────────────────────────

def test_blast_radius_transitive(tmp_path):
    root = make_pkg(tmp_path)
    g = codegraph.build_graph(codegraph.scan_code(root), root)
    assert codegraph.blast_radius(g, "pkg.utils") == {"pkg.core", "pkg.api"}
    assert codegraph.blast_radius(g, "pkg.core") == {"pkg.api"}
    assert codegraph.blast_radius(g, "pkg.api") == set()


# ──────────────────────────────────────────────
# 7. detect_clusters — connected components
# ──────────────────────────────────────────────

def test_detect_clusters_separates_lonely(tmp_path):
    root = make_pkg(tmp_path)
    g = codegraph.build_graph(codegraph.scan_code(root), root)
    clusters = codegraph.detect_clusters(g)
    assert {"pkg.api", "pkg.core", "pkg.utils"} in clusters
    assert {"pkg.lonely"} in clusters


# ──────────────────────────────────────────────
# 8. generate_output — writes CODEMAP.md, never touches source
# ──────────────────────────────────────────────

def test_generate_output_writes_codemap_and_keeps_source(tmp_path):
    root = make_pkg(tmp_path)
    g = codegraph.build_graph(codegraph.scan_code(root), root)
    before = (root / "pkg" / "core.py").read_text(encoding="utf-8")

    out = tmp_path / "out"
    codegraph.generate_output(g, out, root)

    codemap = (out / "CODEMAP.md").read_text(encoding="utf-8")
    assert "God Nodes" in codemap
    assert "Blast Radius" in codemap
    assert "pkg.utils" in codemap
    # source files are never modified
    assert (root / "pkg" / "core.py").read_text(encoding="utf-8") == before


# ══════════════════════════════════════════════
# Scope-out extensions: multi-language + modularity clustering
# ══════════════════════════════════════════════

# ── JS/TS fixture ──────────────────────────────

def make_js_proj(tmp_path: Path) -> Path:
    root = tmp_path / "webapp"
    src = root / "src"
    src.mkdir(parents=True)
    (src / "b.ts").write_text("export const b = 1;\n", encoding="utf-8")
    (src / "a.ts").write_text(textwrap.dedent('''\
        import { b } from "./b";
        export function doA() { return b; }
    '''), encoding="utf-8")
    (src / "app.tsx").write_text(textwrap.dedent('''\
        import React from "react";
        import { doA } from "./a";
        export class App {}
    '''), encoding="utf-8")
    nm = root / "node_modules" / "react"
    nm.mkdir(parents=True)
    (nm / "index.js").write_text("module.exports = {};\n", encoding="utf-8")
    return root


def test_scan_code_multilang_finds_js_ts_rs(tmp_path):
    root = make_js_proj(tmp_path)
    files = codegraph.scan_code(root)
    names = {p.name for p in files}
    assert {"a.ts", "b.ts", "app.tsx"} <= names
    assert "index.js" not in names   # node_modules excluded


def test_module_name_path_based_for_js(tmp_path):
    root = make_js_proj(tmp_path)
    assert codegraph.module_name(root / "src" / "a.ts", root) == "src/a"


def test_js_relative_import_is_internal_edge(tmp_path):
    root = make_js_proj(tmp_path)
    g = codegraph.build_graph(codegraph.scan_code(root), root)
    assert "src/b" in g.successors("src/a")          # ./b resolved
    assert g.edge_kind("src/a", "src/b") == "internal"


def test_js_bare_specifier_is_external(tmp_path):
    root = make_js_proj(tmp_path)
    g = codegraph.build_graph(codegraph.scan_code(root), root)
    assert "react" in g.node_attr("src/app")["external_imports"]
    assert "src/a" in g.successors("src/app")         # ./a resolved
    assert "react" not in g.successors("src/app")


# ── Rust fixture ───────────────────────────────

def make_rust_proj(tmp_path: Path) -> Path:
    root = tmp_path / "crate"
    src = root / "src"
    src.mkdir(parents=True)
    (src / "util.rs").write_text("pub fn helper() -> i32 { 42 }\n", encoding="utf-8")
    (src / "lib.rs").write_text(textwrap.dedent('''\
        mod util;
        use std::collections::HashMap;

        pub struct Engine;

        pub fn run() -> i32 { util::helper() }
    '''), encoding="utf-8")
    return root


def test_rust_mod_is_internal_edge(tmp_path):
    root = make_rust_proj(tmp_path)
    g = codegraph.build_graph(codegraph.scan_code(root), root)
    assert "src/util" in g.successors("src/lib")      # `mod util;`
    assert "Engine" in g.node_attr("src/lib")["classes"]
    assert "run" in g.node_attr("src/lib")["functions"]
    assert "std" in g.node_attr("src/lib")["external_imports"]


# ── Modularity clustering ──────────────────────

def test_detect_clusters_modularity_splits_two_triangles():
    """Two triangles joined by one bridge edge must split into 2 communities
    (connected-components would wrongly return a single cluster)."""
    g = codegraph.CodeGraph()
    for n in ["a", "b", "c", "x", "y", "z"]:
        g.add_node(n)
    for s, d in [("a", "b"), ("b", "c"), ("c", "a")]:
        g.add_edge(s, d)
    for s, d in [("x", "y"), ("y", "z"), ("z", "x")]:
        g.add_edge(s, d)
    g.add_edge("c", "x")  # bridge

    clusters = codegraph.detect_clusters(g)
    assert {"a", "b", "c"} in clusters
    assert {"x", "y", "z"} in clusters
