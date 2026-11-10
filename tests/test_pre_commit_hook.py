"""Tests for repo-security/scripts/pre-commit.sh — the shared 3+1 layer commit guardrail.

The hook is distributed to every project repository, so a regression here
breaks all of them at once. Each test drives the real hook through a real
`git commit` in a throwaway repository.
"""

import pathlib
import shutil
import subprocess

import pytest

HOOK_SRC = (pathlib.Path(__file__).resolve().parents[1]
            / "claude" / "skills" / "repo-security" / "scripts" / "pre-commit.sh")

# 衝突マーカーは動的に組み立てる。このテストファイル自身が行頭マーカーを
# 含むと、フックに阻まれて自分をコミットできなくなるため。
OURS = "<" * 7
BASE = "|" * 7
SEP = "=" * 7
THEIRS = ">" * 7

CONFLICT_CONTENT = "\n".join([
    "---",
    "tags: [graph-import, auto-generated]",
    f"{OURS} HEAD",
    "source_file: /home/runner/work/app/app/notes/a.md",
    SEP,
    "source_file: ~/Project/app/notes/a.md",
    f"{THEIRS} 1234567 (chore: refresh knowledge graph)",
    "---",
    "",
])

DIFF3_CONTENT = "\n".join([
    f"{OURS} HEAD",
    "new",
    f"{BASE} base",
    "original",
    SEP,
    "other",
    f"{THEIRS} 1234567 (other)",
    "",
])


def run(cmd, cwd):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path):
    """A git repository with the real hook installed."""
    path = tmp_path / "repo"
    path.mkdir()
    run(["git", "init", "-q", "."], path)
    run(["git", "config", "user.name", "test"], path)
    run(["git", "config", "user.email", "test@example.com"], path)
    hook = path / ".git" / "hooks" / "pre-commit"
    shutil.copy(HOOK_SRC, hook)
    hook.chmod(0o755)
    return path


def commit(repo, name, content, message="test"):
    """Write one file, stage it, and attempt a commit."""
    target = repo / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    run(["git", "add", name], repo)
    return run(["git", "commit", "-m", message], repo)


def output(result):
    """git routes hook output to stderr — judge on both streams."""
    return result.stdout + result.stderr


# ── 衝突マーカーを止める ──────────────────────────────────────────────
def test_blocks_conflict_markers(repo):
    result = commit(repo, "notes/graph-imports/INDEX.md", CONFLICT_CONTENT)
    assert result.returncode != 0
    assert "衝突マーカー" in output(result)


def test_blocks_diff3_base_marker(repo):
    result = commit(repo, "notes/a.md", DIFF3_CONTENT)
    assert result.returncode != 0


def test_names_the_offending_file(repo):
    result = commit(repo, "notes/graph-imports/INDEX.md", CONFLICT_CONTENT)
    assert "notes/graph-imports/INDEX.md" in output(result)


# ── 誤検出しない ─────────────────────────────────────────────────────
def test_allows_clean_file(repo):
    result = commit(repo, "notes/a.md", "# Title\n\nplain content\n")
    assert result.returncode == 0


def test_allows_markdown_setext_heading(repo):
    """Markdown の setext 見出しは `=======` 行になる。誤検出してはならない。"""
    result = commit(repo, "notes/a.md", "Title\n=======\n\nbody\n")
    assert result.returncode == 0


def test_allows_inline_mention_in_docs(repo):
    """行頭でない言及（バッククォート内の解説）は通す。"""
    content = f"本文中で `{OURS} HEAD` に触れる解説。\n"
    result = commit(repo, "notes/system/explain.md", content)
    assert result.returncode == 0


def test_allows_the_hook_itself(repo):
    """フック自身は検出パターンを含むため自己衝突させない。"""
    result = commit(repo, "setup/pre-commit.sh", HOOK_SRC.read_text(encoding="utf-8"))
    assert result.returncode == 0


def test_skips_binary_files(repo):
    """バイナリを誤って掴まない。"""
    target = repo / "data.bin"
    target.write_bytes(b"\x00\x01" + f"{OURS} HEAD\n".encode() + b"\x02\xff")
    run(["git", "add", "data.bin"], repo)
    result = run(["git", "commit", "-m", "binary"], repo)
    assert result.returncode == 0


# ── 既存レイヤーの回帰 ───────────────────────────────────────────────
def test_still_blocks_anthropic_key(repo):
    result = commit(repo, "config.py", 'KEY = "sk-ant-' + "A" * 20 + '"\n')
    assert result.returncode != 0


def test_still_blocks_env_file(repo):
    result = commit(repo, ".env", "TOKEN=x\n")
    assert result.returncode != 0

# ── Layer 1 の自己衝突回避 ───────────────────────────────────────────
# セキュリティポリシー文書は検出文字列を「禁止例」として列挙するため、
# 自分自身に阻まれて編集できなくなる。除外対象であることを固定する。
INJECTION_DOC = "ポリシー例: " + "ignore previous " + "instructions を検出する\n"


@pytest.mark.parametrize(
    "name",
    [
        "setup/security-setup-record.md",
        "setup/security-check.yml",
        "docs/secret_governance_policy.md",
    ],
)
def test_allows_security_policy_docs(repo, name):
    result = commit(repo, name, INJECTION_DOC)
    assert result.returncode == 0, output(result)


def test_still_blocks_injection_in_normal_files(repo):
    result = commit(repo, "src/app.py", INJECTION_DOC)
    assert result.returncode != 0
