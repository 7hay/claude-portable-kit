#!/bin/bash
# SessionStart hook: remind when the security check has not run for 7+ days.
CLAUDE_HOME="${CLAUDE_HOME:-$HOME/.claude}"
TIMESTAMP_FILE="$CLAUDE_HOME/security_check_last_run"
THRESHOLD_SEC=$((7 * 86400))
CMD="bash $CLAUDE_HOME/skills/repo-security/scripts/claude-security-check.sh <リポジトリのパス>"

if [ ! -f "$TIMESTAMP_FILE" ]; then
    printf '{"systemMessage": "⚠️ セキュリティチェック未実行\\n%s を実行してください（または「セキュリティチェックして」と依頼）。"}\n' "$CMD"
    exit 0
fi

ELAPSED=$(( $(date +%s) - $(cat "$TIMESTAMP_FILE") ))
if [ "$ELAPSED" -gt "$THRESHOLD_SEC" ]; then
    printf '{"systemMessage": "⚠️ セキュリティチェックから %d 日経過しています。\\n%s を実行してください。"}\n' \
        "$((ELAPSED / 86400))" "$CMD"
fi
