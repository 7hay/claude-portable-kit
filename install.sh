#!/usr/bin/env bash
# install.sh — install claude-portable-kit into ~/.claude (non-destructive)
#
#   bash install.sh            # install / update
#   bash install.sh --dry-run  # show what would change, write nothing
#
# - Files that differ from the kit are backed up to ~/.claude/backups/ before overwrite
# - An existing CLAUDE.md is never touched (the template goes to CLAUDE.portable.md)
# - settings.json is merged (deny rules + hooks added), never replaced
# - CLAUDE_HOME overrides the target directory (used by tests)
set -euo pipefail

KIT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$KIT/claude"
CLAUDE_HOME="${CLAUDE_HOME:-$HOME/.claude}"
DRY_RUN=""
[ "${1:-}" = "--dry-run" ] && DRY_RUN="--dry-run"
BACKUP_DIR="$CLAUDE_HOME/backups/portable-kit-$(date +%Y%m%d_%H%M%S)"
CHANGED=0

say() { printf '%s\n' "$*"; }

command -v python3 >/dev/null || { say "❌ python3 が必要です"; exit 1; }

say "📦 claude-portable-kit → $CLAUDE_HOME ${DRY_RUN:+(dry-run: 何も書き込みません)}"

# 1) settings.json を先に検証する（壊れていたら何も書かずに中止するため）
python3 "$KIT/lib/merge_settings.py" "$CLAUDE_HOME/settings.json" \
    "$SRC/settings.template.json" "$CLAUDE_HOME" --dry-run >/dev/null

# copy_file <src> <dst>: identical → skip / differs → backup then overwrite
copy_file() {
    local src="$1" dst="$2" rel="${2#"$CLAUDE_HOME"/}"
    if [ -f "$dst" ] && cmp -s "$src" "$dst"; then
        return
    fi
    CHANGED=$((CHANGED + 1))
    if [ -n "$DRY_RUN" ]; then
        say "  [dry-run] $( [ -f "$dst" ] && echo 更新 || echo 追加 ): $rel"
        return
    fi
    if [ -f "$dst" ]; then
        mkdir -p "$BACKUP_DIR/$(dirname "$rel")"
        cp -p "$dst" "$BACKUP_DIR/$rel"
        say "  更新: $rel（旧版をバックアップ）"
    else
        say "  追加: $rel"
    fi
    mkdir -p "$(dirname "$dst")"
    cp "$src" "$dst"
    case "$dst" in *.sh|*.py) chmod +x "$dst" ;; esac
}

# 2) skills / agents / hooks
while IFS= read -r -d '' f; do
    copy_file "$f" "$CLAUDE_HOME/${f#"$SRC"/}"
done < <(find "$SRC/skills" "$SRC/agents" "$SRC/hooks" -type f \
            -not -path '*/__pycache__/*' -print0 | sort -z)

# 3) CLAUDE.md — 既存があれば絶対に触らない
if [ -e "$CLAUDE_HOME/CLAUDE.md" ] || [ -L "$CLAUDE_HOME/CLAUDE.md" ]; then
    copy_file "$SRC/CLAUDE.template.md" "$CLAUDE_HOME/CLAUDE.portable.md"
    CLAUDE_MD_NOTE="既存の CLAUDE.md は変更していません。CLAUDE.portable.md と見比べて必要な節を取り込んでください。"
else
    copy_file "$SRC/CLAUDE.template.md" "$CLAUDE_HOME/CLAUDE.md"
    CLAUDE_MD_NOTE="CLAUDE.md を作成しました。末尾の「この環境について」を記入してください。"
fi

# 4) settings.json を統合
[ -z "$DRY_RUN" ] && mkdir -p "$CLAUDE_HOME"
python3 "$KIT/lib/merge_settings.py" "$CLAUDE_HOME/settings.json" \
    "$SRC/settings.template.json" "$CLAUDE_HOME" $DRY_RUN

say ""
if [ "$CHANGED" -eq 0 ]; then
    say "✅ ファイルはすべて最新です"
else
    say "✅ ${CHANGED} ファイルを反映${DRY_RUN:+予定}"
fi
say "📝 $CLAUDE_MD_NOTE"
command -v jq >/dev/null || say "⚠️  jq が未インストールのためステータスラインは表示されません（sudo apt install jq）"
command -v gh >/dev/null || say "ℹ️  gh CLI が未インストールのため gh-actions-check は使えません"
say "👉 Claude Code を再起動すると Skill・設定が有効になります"
