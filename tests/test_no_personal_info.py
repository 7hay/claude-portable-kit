"""Guard: the kit must stay free of machine- or person-specific information.

This repository is meant to be public and portable. Two layers:
  1. Generic patterns (absolute home paths, e-mail addresses) — always on.
  2. Optional local patterns from `.personal-patterns` (git-ignored), one
     regex per line. Put your own user name, project names, cloud project
     IDs, etc. there so they are caught without being published.
"""

import pathlib
import re
import subprocess

import pytest

KIT = pathlib.Path(__file__).resolve().parents[1]
LOCAL_PATTERNS = KIT / ".personal-patterns"

GENERIC = [
    # /home/<name>/ — GitHub Actions runner path is allowed
    r"/home/(?!runner\b)[A-Za-z0-9_.-]+/",
    r"/Users/[A-Za-z0-9_.-]+/",
    r"C:\\\\Users\\\\[A-Za-z0-9_.-]+",
    # e-mail (example.com / anthropic noreply are fine)
    r"[A-Za-z0-9._%+-]+@(?!example\.com|anthropic\.com)[A-Za-z0-9.-]+\.[a-z]{2,}",
]


def local_patterns():
    if not LOCAL_PATTERNS.exists():
        return []
    lines = LOCAL_PATTERNS.read_text(encoding="utf-8").splitlines()
    return [ln.strip() for ln in lines if ln.strip() and not ln.startswith("#")]


def distributed_files():
    """Files git would publish (tracked + untracked-but-not-ignored)."""
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=KIT, capture_output=True, text=True, check=True,
    ).stdout.split()
    return [KIT / p for p in out if (KIT / p).is_file()]


@pytest.mark.parametrize("pattern", GENERIC + local_patterns())
def test_no_personal_info(pattern):
    rx = re.compile(pattern, re.I)
    hits = []
    for path in distributed_files():
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for no, line in enumerate(text.splitlines(), 1):
            if rx.search(line):
                hits.append(f"{path.relative_to(KIT)}:{no}: {line.strip()[:80]}")
    assert not hits, "personal/env-specific info found:\n" + "\n".join(hits)


def test_personal_patterns_file_is_ignored():
    """ローカル専用の検出リストそのものが公開されてはならない。"""
    result = subprocess.run(
        ["git", "check-ignore", ".personal-patterns"], cwd=KIT, capture_output=True,
    )
    assert result.returncode == 0
