# claude-portable-kit

Claude Code 用の **汎用 Skill・セキュリティ設定・開発ルール** を、どの PC にも数分で移植するためのキット。
特定のプロジェクトや個人環境に依存するものは含みません。

## 入っているもの

| 種類 | 名前 | 何をするか | 呼び出し例 |
|---|---|---|---|
| Skill | `codegraph` | コードの地図（CODEMAP.md）を作り、全ソースを読まずに構造を把握 | 「コードグラフを作って」 |
| Skill | `doc-audit` | ドキュメントと実装のズレを検出（報告のみ） | 「ドキュメント監査して」 |
| Skill | `doc-sync` | 実装後に関連ドキュメントを「置換」で同期 | 「ドキュメントを同期して」 |
| Skill | `gh-actions-check` | GitHub Actions の状態確認と失敗原因の特定 | 「CIの状態を見て」 |
| Skill | `infra-incident` | 障害報告書（ポストモーテム）を定型で作成 | 「障害報告書の草案を作って」 |
| Skill | `repo-security` | セキュリティ点検＋pre-commit フック／CI の導入 | 「セキュリティチェックして」 |
| Agent | `security-auditor` / `code-architect` / `test-generator` | 監査・設計・テスト生成の専門サブエージェント | 「security-auditor で監査して」 |
| 設定 | 機密ファイル Read 禁止ルール | `.env`・`~/.ssh` 等を Claude が読めないよう強制 | （自動） |
| 設定 | 起動時リマインド | 7日以上セキュリティ点検をしていないと通知 | （自動） |
| 設定 | ステータスライン | ディレクトリ・ブランチ・モデル・コンテキスト使用率を表示 | （自動） |
| ルール | `CLAUDE.md` テンプレート | 7段階 Work Process・Git／ファイル操作ルール・セキュリティポリシー | （自動） |

Skill は Claude Code 公式形式（`~/.claude/skills/<名前>/SKILL.md`）なので、`/repo-security` のように
直接呼ぶことも、話の流れから Claude が自動で使うこともできます。

## 移植手順（3ステップ）

### 前提

- Claude Code がインストール済み（`claude --version` で確認）
- `git` と `python3` がある（Mac / Linux / WSL は通常入っています）
- 任意: `jq`（ステータスライン用）、`gh`（GitHub Actions 確認用）

### Step 1. キットを取得する

```bash
mkdir -p ~/Project && cd ~/Project
git clone https://github.com/<your-account>/claude-portable-kit.git
cd claude-portable-kit
```

### Step 2. 予行演習してからインストールする

```bash
bash install.sh --dry-run   # 何が追加・更新されるかを表示するだけ（書き込みなし）
bash install.sh             # 実際にインストール
```

インストーラーは**既存環境を壊さない**ように作ってあります。

| 対象 | 既に存在する場合の動き |
|---|---|
| `CLAUDE.md` | **一切触らない**。テンプレートは `CLAUDE.portable.md` として横に置く |
| `settings.json` | 置き換えず**統合**。拒否ルールとフックを追加するだけで、モデル設定や既存フックは残す |
| ステータスライン | 既に設定があればそちらを優先 |
| Skill・Agent ファイル | 内容が違えば `~/.claude/backups/portable-kit-<日時>/` に退避してから更新 |

何度実行しても同じ結果になる（冪等）ので、キットを更新したら `git pull && bash install.sh` するだけです。

### Step 3. 仕上げと動作確認

1. **CLAUDE.md を整える**
   - 新規作成された場合: 末尾の「この環境について」に OS・プロジェクトの場所などを書く
   - 既存があった場合: `~/.claude/CLAUDE.portable.md` と見比べ、欲しい節をコピーする
2. **Claude Code を再起動**（VS Code ならウィンドウの再読み込み）
3. **確認**: Claude Code で `/skills` を開き、6つの Skill が並んでいれば成功。
   続けて「このリポジトリのセキュリティチェックして」と頼むと `repo-security` が動きます
4. **リポジトリごとにガードを入れる**: 作業する各リポジトリで「pre-commit を入れて」と依頼
   （`.git/hooks/` は clone で配布されないため、リポジトリごとに1回必要）

## アンインストール

`~/.claude/skills/` 配下の6フォルダ、`~/.claude/agents/` の3ファイル、`~/.claude/hooks/` の2ファイルを削除し、
`~/.claude/settings.json` から `security-remind.sh` のフックと不要な拒否ルールを外します。
退避した旧版は `~/.claude/backups/` にあります。

## キットを育てる（メンテナンス）

```bash
python3 -m pytest tests -q   # インストーラー・設定統合・pre-commit・codegraph・個人情報混入を検査
```

- 新しい Skill は `claude/skills/<name>/SKILL.md` に追加（先頭の `name` はフォルダ名と一致させる）。
  テストの `SKILLS` リストにも追加する
- **個人情報の混入チェック**: `tests/test_no_personal_info.py` が、`/home/<ユーザー名>/` などの絶対パスと
  メールアドレスを常に検出します。自分のユーザー名・プロジェクト名などは Git 管理外の
  `.personal-patterns`（1行1正規表現）に書くと、公開せずに検出対象へ加えられます
- このリポジトリ自身にも pre-commit フックを入れておくと安全です:
  `cp claude/skills/repo-security/scripts/pre-commit.sh .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit`

## 構成

```
claude-portable-kit/
├── install.sh                  # インストーラー（--dry-run 対応）
├── lib/merge_settings.py       # settings.json の非破壊マージ
├── claude/                     # ~/.claude に配置されるもの
│   ├── CLAUDE.template.md
│   ├── settings.template.json
│   ├── skills/<name>/SKILL.md  (+ scripts/)
│   ├── agents/*.md
│   └── hooks/*.sh
└── tests/
```
