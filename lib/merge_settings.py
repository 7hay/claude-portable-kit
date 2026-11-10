#!/usr/bin/env python3
"""Merge the kit's settings template into an existing ~/.claude/settings.json.

Rules (non-destructive by design):
  - permissions.deny : union, existing order first, no duplicates
  - hooks.<event>    : add a template hook only if its command is not present
  - statusLine       : set only when the user has none
  - everything else  : untouched

Usage: merge_settings.py <settings.json> <template.json> <claude_home> [--dry-run]
Exit 1 (and leave the file as-is) when the existing settings.json is not valid JSON.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

PLACEHOLDER = "__CLAUDE_HOME__"


def _commands(groups: list[dict]) -> set[str]:
    return {h.get("command") for g in groups for h in g.get("hooks", [])}


def merge(base: dict, template: dict) -> dict:
    out = copy.deepcopy(base)

    deny = out.setdefault("permissions", {}).setdefault("deny", [])
    for rule in template.get("permissions", {}).get("deny", []):
        if rule not in deny:
            deny.append(rule)

    for event, groups in template.get("hooks", {}).items():
        current = out.setdefault("hooks", {}).setdefault(event, [])
        for group in groups:
            new_cmds = {h.get("command") for h in group.get("hooks", [])}
            if not new_cmds & _commands(current):
                current.append(copy.deepcopy(group))

    if "statusLine" in template and "statusLine" not in out:
        out["statusLine"] = copy.deepcopy(template["statusLine"])

    return out


def main(argv: list[str]) -> int:
    settings_path, template_path, claude_home = map(Path, argv[1:4])
    dry_run = "--dry-run" in argv

    raw = template_path.read_text(encoding="utf-8").replace(PLACEHOLDER, str(claude_home))
    template = json.loads(raw)

    base: dict = {}
    if settings_path.exists():
        try:
            base = json.loads(settings_path.read_text(encoding="utf-8") or "{}")
        except json.JSONDecodeError as e:
            print(f"❌ {settings_path} が JSON として壊れています（{e}）。"
                  "手で直してから再実行してください。ファイルは変更していません。",
                  file=sys.stderr)
            return 1

    merged = merge(base, template)
    if merged == base:
        print("  settings.json: 変更なし")
        return 0
    if dry_run:
        print("  [dry-run] settings.json を更新予定")
        return 0
    settings_path.write_text(json.dumps(merged, indent=2, ensure_ascii=False) + "\n",
                             encoding="utf-8")
    print("  settings.json: 拒否ルール・フックを追加しました")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
