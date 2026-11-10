"""
Tests for codegraph_registry.py (Shared Brain)
Run: python3 -m pytest tests/test_codegraph_registry.py -v

Phase A: 全プロジェクトを横断して各 CODEMAP を生成し、1つの REGISTRY.md に集約する。
"""

import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "claude" / "skills" / "codegraph" / "scripts"))
import codegraph_registry as reg


def make_base(tmp_path: Path) -> Path:
    base = tmp_path / "Projects"
    # alpha: a tiny Python project
    a = base / "alpha" / "pkg"
    a.mkdir(parents=True)
    (a / "__init__.py").write_text("", encoding="utf-8")
    (a / "m.py").write_text(textwrap.dedent('''\
        """Module M."""
        import os
        def f():
            return os.getcwd()
    '''), encoding="utf-8")
    # beta: a tiny TS project
    b = base / "beta" / "src"
    b.mkdir(parents=True)
    (b / "x.ts").write_text("export const x = 1;\n", encoding="utf-8")
    (b / "y.ts").write_text('import { x } from "./x";\nexport const y = x;\n', encoding="utf-8")
    # empty: no source files -> must be skipped
    empty = base / "empty"
    empty.mkdir()
    (empty / "README.md").write_text("# nothing here\n", encoding="utf-8")
    return base


def test_discover_projects_skips_dirs_without_source(tmp_path):
    base = make_base(tmp_path)
    projects = reg.discover_projects(base)
    assert {p.name for p in projects} == {"alpha", "beta"}


def test_project_summary_fields(tmp_path):
    base = make_base(tmp_path)
    s = reg.project_summary(base / "alpha")
    assert s["name"] == "alpha"
    assert s["modules"] >= 2
    assert "python" in s["languages"]
    assert s["source_tokens"] > 0
    assert s["codemap_tokens"] > 0
    assert s["saved_tokens"] == max(0, s["source_tokens"] - s["codemap_tokens"])


def test_render_registry_lists_projects(tmp_path):
    base = make_base(tmp_path)
    summaries = [reg.project_summary(p) for p in reg.discover_projects(base)]
    md = reg.render_registry(summaries)
    assert "alpha" in md
    assert "beta" in md
    assert "Shared Brain" in md


def test_build_registry_writes_files_and_keeps_sources(tmp_path):
    base = make_base(tmp_path)
    before = (base / "alpha" / "pkg" / "m.py").read_text(encoding="utf-8")

    out = tmp_path / "registry"
    summaries = reg.build_registry(reg.discover_projects(base), out)

    assert (out / "REGISTRY.md").exists()
    assert (out / "alpha" / "CODEMAP.md").exists()
    assert (out / "beta" / "CODEMAP.md").exists()
    assert len(summaries) == 2
    # source files are never modified
    assert (base / "alpha" / "pkg" / "m.py").read_text(encoding="utf-8") == before
