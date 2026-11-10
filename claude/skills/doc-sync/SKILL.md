---
name: doc-sync
description: After a code change, update every related .md file so docs match reality — rewrite or delete stale statements instead of only appending, keep MEMORY.md under 200 lines, and check for leaked secrets. Use right after implementation or before committing, or when asked 「ドキュメントを同期して」「doc-sync」「今の変更をドキュメントに反映して」.
---

# Doc Sync（実装完了後のドキュメント同期）

原則: **ドキュメントの更新は「追記」ではなく「置換」**。矛盾する古い記述を残さない。

## Step 1: 波及ファイルの洗い出し

変更したファイル名・機能名・フェーズ名・バージョン番号で横断検索する。

```bash
git diff --name-only HEAD~1          # 今回変えたファイル
git grep -n -l "<機能名|旧バージョン番号>" -- '*.md'
MEM=~/.claude/projects/$(pwd | sed 's/[^A-Za-z0-9]/-/g')/memory
grep -rln "<機能名>" "$MEM" 2>/dev/null
```

## Step 2: 更新方針を決める

| 状況 | アクション |
|---|---|
| 完了のまま内容が変わった | リライト（古い記述は削除） |
| 未着手 → 完了 | ステータス更新 + コミットハッシュ |
| バージョン・フェーズ番号が古い | 数値を置換（古い値は残さない） |
| 「次の課題」が達成済み | 削除して新しい次の課題に置き換え |

## Step 3: MEMORY.md を 200 行以内に保つ

```bash
wc -l "$MEM/MEMORY.md"
```

超える場合は ①完了済み詳細を1行に要約 → ②重複統合 → ③詳細は個別ファイルへ移し MEMORY.md にはリンクのみ。

## Step 4: 混入チェック

```bash
# [E] は「E の1文字」の意味。検出対象の文字列をそのまま書くと pre-commit フックが
# このファイル自体を止めてしまうため、正規表現で同じ意味を表現している
git grep -n -E "YOUR_.*KEY|TODO_SECR[E]T|INSERT_SECR[E]T|REPLACE_M[E]" -- '*.md'
git grep -n -E "sk-ant-|github_pat_|AKIA[0-9A-Z]{16}|BEGIN [A-Z ]*PRIVATE KEY"
```

## 報告フォーマット

```markdown
## Doc Sync 完了レポート（YYYY-MM-DD）
| ファイル:行 | 更新項目 | 変更前 | 変更後 |
|---|---|---|---|

MEMORY.md 行数: XX行（制限内 ✅）
シークレット混入: なし ✅
```

コミットはユーザーの承認を得てから行う。
