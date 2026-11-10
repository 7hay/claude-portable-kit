---
name: repo-security
description: Run the repository security check and install guardrails into a git repo — a 4-layer pre-commit hook (prompt-injection strings, .env/key files, merge-conflict markers, live API keys) and a GitHub Actions security workflow with gitleaks. Use when asked 「セキュリティチェックして」「このリポジトリにガードを入れて」「pre-commitを入れて」, when creating a new repository, or when the 7-day security reminder appears.
---

# Repo Security（リポジトリのセキュリティ点検とガード導入）

スクリプトは `~/.claude/skills/repo-security/scripts/` にある。

## 1. 点検（読み取りのみ・安全）

```bash
bash ~/.claude/skills/repo-security/scripts/claude-security-check.sh <リポジトリのパス>
```

`.gitignore`・`.env` の履歴・pre-commit 導入有無・不審文字列・平文シークレットを確認し、
実行日時を記録する（7日経つと起動時にリマインドが出る）。

## 2. pre-commit フック導入（ユーザー確認後）

```bash
cd <リポジトリ>
cp ~/.claude/skills/repo-security/scripts/pre-commit.sh .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

| Layer | 止めるもの |
|---|---|
| 1 | プロンプトインジェクション文字列 |
| 2 | `.env` / `.key` / `.pem` / `.p12` ファイル |
| 3 | 解決し忘れたマージ衝突マーカー |
| 4 | 生の API キー（Anthropic / GitHub / AWS / GCP / 秘密鍵ブロック）とプレースホルダー |

既に `.git/hooks/pre-commit` がある場合は上書きせず、中身を見せて統合方法を相談する。
`.git/hooks/` は clone しても配布されないため、**リポジトリごとに導入が必要**。

## 3. GitHub Actions（ユーザー確認後）

```bash
mkdir -p .github/workflows
cp ~/.claude/skills/repo-security/scripts/security-check.yml .github/workflows/
```

push / PR ごとに機密ファイル・インジェクション文字列・gitleaks スキャンを実行する。
ローカルの pre-commit は `--no-verify` で迂回できるため、サーバー側の二重チェックとして入れる。

## 鍵が漏れていた場合

1. **最優先で鍵をローテーション（失効→再発行）**。履歴から消しても、一度 push した鍵は漏洩済み扱い
2. その後 `git filter-repo` 等で履歴から除去
3. 鍵は `.env`（Git 管理外）かクラウドの Secret Manager に置き、コードからは名前で参照する
