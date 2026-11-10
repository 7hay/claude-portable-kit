---
name: gh-actions-check
description: Check GitHub Actions CI/CD status across one or more repositories with the gh CLI and diagnose failed runs. Use when asked 「GitHub Actionsを確認して」「CIの状態を見て」 or after pushing.
---

# GH Actions Check（GitHub Actions の状態確認）

## 実行手順

```bash
# カレントリポジトリ
gh run list --limit 10

# 自分の全リポジトリ（直近更新順）をまとめて確認
OWNER=$(gh api user --jq .login)
for repo in $(gh repo list "$OWNER" --limit 20 --json name --jq '.[].name'); do
  echo "=== $repo ==="
  gh run list --repo "$OWNER/$repo" --limit 3 2>/dev/null || echo "(workflow なし)"
done

# 失敗の詳細（ログの失敗部分だけ）
gh run view <RUN_ID> --repo <owner>/<repo> --log-failed
```

> `gh run list` は `--repo` なしだと Git リポジトリ内でしか動かない。ループでは必ず付ける。

## 確認ポイント

1. `failure` / `cancelled` がないか
2. main への直近 push の CI が通っているか
3. 定期実行（`schedule:`）のワークフローが止まっていないか
   — GitHub は 60 日間 push のないリポジトリの schedule を自動停止する

## よくあるトラブル

| 症状 | 対処 |
|---|---|
| `gh: Not logged in` | `gh auth login` |
| Secret 未設定エラー | `gh secret list --repo <repo>` で確認 |
| PAT の期限切れ（401/403） | トークンを再発行し Secret を再登録。期限をカレンダーに記録 |
| schedule が動かない | Actions タブで workflow を再有効化 |
