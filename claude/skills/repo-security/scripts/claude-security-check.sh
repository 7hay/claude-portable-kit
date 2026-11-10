#!/bin/bash
# claude-security-check.sh — periodic security check for a repository used with Claude Code
# Usage: bash ~/.claude/skills/repo-security/scripts/claude-security-check.sh [repo path]

PROJECT=${1:-.}
CLAUDE_HOME="${CLAUDE_HOME:-$HOME/.claude}"

# 以降の git / grep はすべて相対パスで動くので、最初に対象リポジトリへ移動する
cd "$PROJECT" || { echo "❌ ディレクトリが見つかりません: $PROJECT"; exit 1; }

echo "=== Claude Code Security Check: $(pwd) ==="
echo "実行日時: $(date)"
echo ""

# 1. CLAUDE.md の存在・整合性確認
echo "--- [1] CLAUDE.md チェック ---"
if [ ! -f "CLAUDE.md" ]; then
    echo "ℹ️  CLAUDE.md なし（プロジェクト固有ルールが不要なら問題なし）"
elif git diff --quiet -- CLAUDE.md 2>/dev/null; then
    echo "✅ CLAUDE.md 改ざんなし（git差分なし）"
else
    echo "⚠️  CLAUDE.md に未コミットの変更あり（意図した変更か確認）:"
    git diff -- CLAUDE.md
fi

# 2. .gitignore 確認
echo ""
echo "--- [2] .gitignore チェック ---"
for pattern in ".env" "*.key" "*.pem" "secrets/"; do
    if grep -qF "$pattern" .gitignore 2>/dev/null; then
        echo "✅ $pattern は除外設定済み"
    else
        echo "⚠️  $pattern が .gitignore に未設定"
    fi
done

# 3. .env の誤コミット確認
echo ""
echo "--- [3] 機密ファイルのgit履歴チェック ---"
if git log --oneline --all -- "*.env" ".env" 2>/dev/null | grep -q .; then
    echo "⚠️  警告: .envファイルのgit履歴あり — git filter-repo / BFG 等で除去し、鍵はローテーション"
else
    echo "✅ .env の誤コミット履歴なし"
fi

# 4. pre-commit フックの導入確認
echo ""
echo "--- [4] pre-commit フック ---"
HOOK="$(git rev-parse --git-path hooks/pre-commit 2>/dev/null)"
if [ -n "$HOOK" ] && [ -x "$HOOK" ]; then
    echo "✅ pre-commit フック導入済み"
else
    echo "⚠️  pre-commit フック未導入 → cp $CLAUDE_HOME/skills/repo-security/scripts/pre-commit.sh .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit"
fi

# 5. インジェクション系文字列の簡易スキャン（未コミットの変更ファイル）
echo ""
echo "--- [5] 不審文字列スキャン ---"
SUSPICIOUS=$(git diff HEAD --name-only 2>/dev/null | \
    grep -v "security-check\|pre-commit" | \
    xargs -r grep -l \
    "ignore previous\|forget your instructions\|jailbreak\|override safety\|disregard all" \
    2>/dev/null)
if [ -n "$SUSPICIOUS" ]; then
    echo "⚠️  要確認ファイル（外部から取り込んだ指示文が混入していないか）:"
    echo "$SUSPICIOUS"
else
    echo "✅ 不審文字列なし（最近の変更ファイル対象）"
fi

# 6. 平文シークレットの簡易チェック
echo ""
echo "--- [6] 平文シークレットチェック（簡易） ---"
HARDCODED=$(grep -rlE \
    "(password|secret|api_key)\s*=\s*['\"][^'\"]{6,}['\"]" . \
    --include="*.py" --include="*.js" --include="*.ts" \
    --exclude-dir=node_modules --exclude-dir=.git --exclude-dir=.venv 2>/dev/null)
if [ -n "$HARDCODED" ]; then
    echo "⚠️  平文シークレットの可能性:"
    echo "$HARDCODED"
else
    echo "✅ 平文シークレット検出なし"
fi

echo ""
echo "=== チェック完了 ==="

# 実行日時を記録（SessionStart フックのリマインド判定に使用）
mkdir -p "$CLAUDE_HOME" && date +%s > "$CLAUDE_HOME/security_check_last_run"
