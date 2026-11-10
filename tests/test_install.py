"""End-to-end tests for install.sh.

Every test installs into a throwaway CLAUDE_HOME, so the real ~/.claude is
never touched.
"""

import json
import os
import pathlib
import re
import subprocess

import pytest

KIT = pathlib.Path(__file__).resolve().parents[1]
INSTALL = KIT / "install.sh"

SKILLS = [
    "codegraph",
    "doc-audit",
    "doc-sync",
    "gh-actions-check",
    "infra-incident",
    "repo-security",
]
AGENTS = ["code-architect.md", "security-auditor.md", "test-generator.md"]
MODEL_ALIASES = {"opus", "sonnet", "haiku", "inherit"}


def install(claude_home, *args):
    env = {**os.environ, "CLAUDE_HOME": str(claude_home)}
    return subprocess.run(
        ["bash", str(INSTALL), *args],
        env=env, capture_output=True, text=True,
    )


def settings(claude_home):
    return json.loads((claude_home / "settings.json").read_text(encoding="utf-8"))


def session_start_commands(data):
    return [
        h["command"]
        for group in data.get("hooks", {}).get("SessionStart", [])
        for h in group.get("hooks", [])
    ]


@pytest.fixture
def home(tmp_path):
    return tmp_path / ".claude"


# ── 新規インストール ──────────────────────────────────────────────
def test_fresh_install_succeeds(home):
    result = install(home)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("name", SKILLS)
def test_skill_installed_in_official_layout(home, name):
    install(home)
    assert (home / "skills" / name / "SKILL.md").is_file()


@pytest.mark.parametrize("name", AGENTS)
def test_agent_installed(home, name):
    install(home)
    assert (home / "agents" / name).is_file()


def test_scripts_are_executable(home):
    install(home)
    for rel in [
        "hooks/security-remind.sh",
        "hooks/statusline-command.sh",
        "skills/repo-security/scripts/pre-commit.sh",
        "skills/repo-security/scripts/claude-security-check.sh",
        "skills/codegraph/scripts/codegraph.py",
    ]:
        assert os.access(home / rel, os.X_OK), rel


def test_creates_claude_md_when_absent(home):
    install(home)
    text = (home / "CLAUDE.md").read_text(encoding="utf-8")
    assert "Work Process" in text


def test_settings_contain_deny_rules_and_hook(home):
    install(home)
    data = settings(home)
    assert "Read(**/.env)" in data["permissions"]["deny"]
    assert "Read(~/.ssh/**)" in data["permissions"]["deny"]
    cmds = session_start_commands(data)
    assert any(str(home / "hooks" / "security-remind.sh") in c for c in cmds)


def test_settings_have_no_unresolved_placeholder(home):
    install(home)
    assert "__CLAUDE_HOME__" not in (home / "settings.json").read_text()


# ── 2回実行しても壊れない（冪等性） ───────────────────────────────
def test_reinstall_does_not_duplicate(home):
    install(home)
    install(home)
    data = settings(home)
    deny = data["permissions"]["deny"]
    assert len(deny) == len(set(deny))
    assert len(session_start_commands(data)) == 1


def test_reinstall_without_changes_makes_no_backup(home):
    install(home)
    install(home)
    assert not (home / "backups").exists() or not any((home / "backups").iterdir())


# ── 既存の設定を壊さない ─────────────────────────────────────────
def test_preserves_existing_settings(home):
    home.mkdir(parents=True)
    (home / "settings.json").write_text(json.dumps({
        "model": "sonnet",
        "permissions": {"deny": ["Read(~/private/**)"], "allow": ["Bash(ls:*)"]},
        "hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "echo hi"}]}]},
        "statusLine": {"type": "command", "command": "echo mine"},
    }))
    assert install(home).returncode == 0
    data = settings(home)
    assert data["model"] == "sonnet"
    assert "Read(~/private/**)" in data["permissions"]["deny"]
    assert data["permissions"]["allow"] == ["Bash(ls:*)"]
    assert "echo hi" in session_start_commands(data)
    assert data["statusLine"]["command"] == "echo mine"  # 既存は上書きしない


def test_keeps_existing_claude_md(home):
    home.mkdir(parents=True)
    (home / "CLAUDE.md").write_text("# my rules\n")
    install(home)
    assert (home / "CLAUDE.md").read_text() == "# my rules\n"
    assert (home / "CLAUDE.portable.md").is_file()


def test_backs_up_modified_skill_before_overwrite(home):
    install(home)
    skill = home / "skills" / "doc-audit" / "SKILL.md"
    skill.write_text("locally edited\n")
    install(home)
    backups = list((home / "backups").rglob("SKILL.md"))
    assert any(b.read_text() == "locally edited\n" for b in backups)


def test_broken_settings_json_is_not_clobbered(home):
    home.mkdir(parents=True)
    (home / "settings.json").write_text("{ broken")
    result = install(home)
    assert result.returncode != 0
    assert (home / "settings.json").read_text() == "{ broken"


# ── --dry-run は何も書かない ─────────────────────────────────────
def test_dry_run_writes_nothing(home):
    result = install(home, "--dry-run")
    assert result.returncode == 0, result.stderr
    assert not home.exists()


# ── 配布物そのものの品質 ─────────────────────────────────────────
FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.S)


@pytest.mark.parametrize("name", SKILLS)
def test_skill_frontmatter(name):
    text = (KIT / "claude" / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
    m = FRONTMATTER.match(text)
    assert m, f"{name}: frontmatter missing"
    fm = m.group(1)
    assert re.search(rf"^name: {re.escape(name)}$", fm, re.M)
    assert re.search(r"^description: .{20,}", fm, re.M)


@pytest.mark.parametrize("name", AGENTS)
def test_agent_uses_model_alias(name):
    """古いモデル ID を固定すると、そのモデルが退役した時点で壊れる。"""
    text = (KIT / "claude" / "agents" / name).read_text(encoding="utf-8")
    m = re.search(r"^model: (\S+)$", text, re.M)
    assert m and m.group(1) in MODEL_ALIASES
