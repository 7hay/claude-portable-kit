#!/bin/bash
# pre-commit hook template — secret guardrail + conflict-marker guard
# Source of truth: claude-portable-kit (claude/skills/repo-security/scripts/pre-commit.sh)
# Install (from inside the target repository):
#   cp ~/.claude/skills/repo-security/scripts/pre-commit.sh .git/hooks/pre-commit
#   chmod +x .git/hooks/pre-commit
#
# Layer 1: Prompt injection strings
# Layer 2: Secret file patterns (.env, .key, .pem, .p12)
# Layer 3: Merge conflict markers left unresolved
# Layer 4: Live secret patterns + placeholders
#          (GCP / Anthropic / GitHub / AWS keys, private key blocks)

STAGED_FILES=$(git diff --cached --name-only --diff-filter=d)

echo "🔍 セキュリティチェック実行中..."

# ── Layer 1: プロンプトインジェクション文字列 ─────────────────────────────
INJECTION_HIT=$(echo "$STAGED_FILES" | \
    grep -v "^\.github/" | \
    grep -v "pre-commit\|pre-push\|security-check\|secret_governance" | \
    grep -v "security-setup-record" | \
    grep -v "^notes/security/" | \
    xargs -r grep -l \
    "ignore previous instructions\|jailbreak\|override safety" \
    2>/dev/null)

if [ -n "$INJECTION_HIT" ]; then
    echo "❌ コミット中止: プロンプトインジェクション文字列を検出"
    echo "$INJECTION_HIT"
    exit 1
fi

# ── Layer 2: 機密ファイルの誤コミット防止 ────────────────────────────────
if echo "$STAGED_FILES" | grep -qE "^\.env$|^\.env\.|/\.env$"; then
    echo "❌ コミット中止: .env ファイルはコミット禁止"
    exit 1
fi

if echo "$STAGED_FILES" | grep -qE "\.(key|pem|p12)$"; then
    echo "❌ コミット中止: 秘密鍵ファイルはコミット禁止"
    exit 1
fi

# ── Layer 3: マージ衝突マーカーの混入防止 ────────────────────────────────
# 生成物（knowledge graph 等）の自動コミットと手元の編集が衝突したまま、
# 解決されずにコミットされるのを防ぐ。マーカーは必ず行頭に現れるので行頭固定で
# 判定し、本文中の言及（解説文でマーカーに触れる場合）は誤検出しない。
# -I でバイナリを除外。フック自身は検出パターンを含むため対象外にする。
CONFLICT_HIT=$(echo "$STAGED_FILES" | \
    grep -v "pre-commit\|pre-push" | \
    xargs -r grep -lIE "^(<<<<<<< |\|\|\|\|\|\|\| |>>>>>>> )" \
    2>/dev/null)

if [ -n "$CONFLICT_HIT" ]; then
    echo "❌ コミット中止: マージ衝突マーカーを検出"
    echo "   該当ファイル: $CONFLICT_HIT"
    echo "   → 衝突を解決してから再コミットしてください"
    echo "     解決中なら git status / git diff で該当箇所を確認できます"
    exit 1
fi

# ── Layer 4: 生鍵パターン・プレースホルダー検出 ───────────────────────────
# 除外対象: このフック自体・ガバナンスポリシー・サンプルファイル
SCAN_FILES=$(echo "$STAGED_FILES" | \
    grep -v "pre-commit\|pre-push" | \
    grep -v "secret_governance_policy" | \
    grep -v "\.sample$")

if [ -z "$SCAN_FILES" ]; then
    echo "✅ セキュリティチェック通過（スキャン対象ファイルなし）"
    exit 0
fi

# One grep per provider so the alert names the leak type.
# Docs are scanned too — real keys must never appear even in documentation.
check_pattern() {
    local label="$1" pattern="$2"
    local hit
    hit=$(echo "$SCAN_FILES" | xargs -r grep -lP "$pattern" 2>/dev/null)
    if [ -n "$hit" ]; then
        echo "❌ コミット中止: ${label} を検出"
        echo "   該当ファイル: $hit"
        echo "   → Secret Manager に格納し、コードからは名前のみ参照してください"
        exit 1
    fi
}

check_pattern "GCP OAuth クライアントシークレット (GOCSPX-)" "GOCSPX-[A-Za-z0-9_-]+"
check_pattern "GCP API キー (AIzaSy...)"                     "AIzaSy[A-Za-z0-9_-]{33}"
check_pattern "Anthropic API キー (sk-ant-...)"              "sk-ant-[A-Za-z0-9_-]{16,}"
check_pattern "GitHub fine-grained PAT (github_pat_...)"     "github_pat_[A-Za-z0-9_]{22,}"
check_pattern "GitHub トークン (ghp_/gho_/ghu_/ghs_/ghr_)"   "gh[pousr]_[A-Za-z0-9]{36}"
check_pattern "AWS アクセスキー (AKIA...)"                   "AKIA[0-9A-Z]{16}"
check_pattern "秘密鍵ブロック (BEGIN ... PRIVATE KEY)"        "BEGIN [A-Z ]*PRIVATE KEY"

# プレースホルダー（将来の生鍵書き込みを誘発する禁止パターン）
# ガバナンス文書（CLAUDE.md・notes/）は「禁止例の説明」として例外扱い
CODE_FILES=$(echo "$SCAN_FILES" | \
    grep -v "^CLAUDE\.md$" | \
    grep -v "^notes/" | \
    grep -v "^\.claude/")

if [ -n "$CODE_FILES" ]; then
    PLACEHOLDER_HIT=$(echo "$CODE_FILES" | xargs -r grep -lP \
        "YOUR_API_KEY|TODO_SECRET|INSERT_SECRET|REPLACE_ME_WITH" 2>/dev/null)
    if [ -n "$PLACEHOLDER_HIT" ]; then
        echo "❌ コミット中止: 生鍵プレースホルダーをコードに検出"
        echo "   該当ファイル: $PLACEHOLDER_HIT"
        echo "   → プレースホルダーは禁止です。Secret Manager 名を直接参照する設計にしてください"
        exit 1
    fi
fi

echo "✅ セキュリティチェック通過"
exit 0
