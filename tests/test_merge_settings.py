"""Unit tests for lib/merge_settings.py (the settings.json merge logic)."""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "lib"))
from merge_settings import merge  # noqa: E402

TEMPLATE = {
    "permissions": {"deny": ["Read(**/.env)", "Read(~/.ssh/**)"]},
    "hooks": {"SessionStart": [{"hooks": [
        {"type": "command", "command": "bash /k/hooks/security-remind.sh", "timeout": 5},
    ]}]},
    "statusLine": {"type": "command", "command": "bash /k/hooks/statusline-command.sh"},
}


def test_merge_into_empty():
    out = merge({}, TEMPLATE)
    assert out["permissions"]["deny"] == ["Read(**/.env)", "Read(~/.ssh/**)"]
    assert out["statusLine"]["command"].endswith("statusline-command.sh")


def test_deny_is_union_preserving_order():
    out = merge({"permissions": {"deny": ["Read(~/.ssh/**)", "Read(x)"]}}, TEMPLATE)
    assert out["permissions"]["deny"] == ["Read(~/.ssh/**)", "Read(x)", "Read(**/.env)"]


def test_hook_not_duplicated():
    once = merge({}, TEMPLATE)
    twice = merge(once, TEMPLATE)
    assert len(twice["hooks"]["SessionStart"]) == 1


def test_other_hook_events_kept():
    base = {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": []}]}}
    out = merge(base, TEMPLATE)
    assert out["hooks"]["PreToolUse"] == base["hooks"]["PreToolUse"]


def test_existing_status_line_wins():
    out = merge({"statusLine": {"type": "command", "command": "mine"}}, TEMPLATE)
    assert out["statusLine"]["command"] == "mine"


def test_input_not_mutated():
    base = {"permissions": {"deny": ["Read(x)"]}}
    merge(base, TEMPLATE)
    assert base == {"permissions": {"deny": ["Read(x)"]}}
