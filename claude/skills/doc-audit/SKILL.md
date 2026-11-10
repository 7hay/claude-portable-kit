---
name: doc-audit
description: Audit drift between documentation (README, CLAUDE.md, MEMORY.md, progress notes) and the actual code/config — false "done" claims, stale versions, contradictions, dead stock, leaked secrets. Use at session start or after a large change, or when asked 「ドキュメント監査して」「doc-audit」「実装とドキュメントのズレを確認して」.
---

# Doc Audit（実装とドキュメントの乖離検出）

「ドキュメントは嘘をつく」前提で、ドキュメントと実態を突き合わせて報告する。
**このスキルは報告のみ。修正は doc-sync で行う。**

## Step 1: 対象ドキュメントを集める

```bash
# プロジェクト内のドキュメント
git ls-files '*.md' | head -50

# Claude Code の自動メモリ（起動ディレクトリごとに保存される）
MEM=~/.claude/projects/$(pwd | sed 's/[^A-Za-z0-9]/-/g')/memory
ls "$MEM" 2>/dev/null || ls -d ~/.claude/projects/*/memory
```

README・CLAUDE.md・MEMORY.md・`progress_*.md` など状態を記述したファイルを優先して読む。

## Step 2: 実態を確認する

```bash
git log --oneline -10            # 最新の実装状況
git status --short               # 未コミットの変更
git tag --sort=-creatordate | head -3   # リリース番号
```

デプロイ先（Cloud Run・Vercel 等）があれば、そのリビジョン / バージョンも CLI で確認する。

## Step 3: 未解決タスクのあぶり出し

```bash
git grep -n -E "TODO|TBD|FIXME|未定|要検討|未着手" -- '*.md' | head -40
```

## Step 4: MEMORY.md の行数

```bash
wc -l "$MEM/MEMORY.md"   # 200行以内か（超えると読み込み時に切り捨てられる）
```

## チェックリスト

| # | 観点 | 確認内容 |
|---|---|---|
| ① | 完了詐称 | 「✅ 完了」なのにコードはスタブ・未実装のまま |
| ② | バージョン漏れ | 最新コミット・リビジョン・フェーズ番号が反映されていない |
| ③ | 矛盾 | 複数ドキュメント間で同じ項目の状態が食い違う |
| ④ | デッドストック | 達成済みの計画・使われないコマンドが残っている |
| ⑤ | MEMORY.md 行数 | 200行以内 |
| ⑥ | 外部依存の再混入 | 廃止したストレージ・ローカル専用パス前提の記述 |
| ⑦ | シークレット混入 | 認証情報の生値・`YOUR_<名前>_KEY` 形式などのプレースホルダー |

## 出力フォーマット

```markdown
## Doc Audit レポート（YYYY-MM-DD）

### 発見した乖離・問題
| # | ファイル:行 | 問題の内容 | 推奨アクション |
|---|---|---|---|

### MEMORY.md 行数: XX行（制限: 200行）
### TODO/TBD 検出: X件
### 異常なし項目
- シークレット混入: なし ✅
```
