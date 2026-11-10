# Claude Code 汎用 Skill 移植手順書（手動インストール版）

この手順書は、`claude-portable-kit` に入っている **汎用 Skill・サブエージェント・セキュリティ設定・開発ルール** を、
インストーラー（`install.sh`）を使わずに **手作業で** 別の PC へ移植するためのものです。

- 所要時間: 約 15〜20 分
- 対象 OS: Linux / macOS / Windows の WSL2（Windows ネイティブは「付録 A」参照）
- 自動で済ませたい場合は、キットの `README.md` の手順（`bash install.sh`）の方が簡単です。
  手動版は「中身を確かめながら入れたい」「一部だけ入れたい」「スクリプト実行が禁止された環境」向けです

---

## 0. 移植されるもの

| 種類 | 名前 | 役割 | 呼び出し例 |
|---|---|---|---|
| Skill | `codegraph` | コードの地図（CODEMAP.md）を作り、全ソースを読まずに構造を把握する | 「コードグラフを作って」 |
| Skill | `doc-audit` | ドキュメントと実装のズレを検出する（報告のみ） | 「ドキュメント監査して」 |
| Skill | `doc-sync` | 実装後に関連ドキュメントを最新状態に書き換える | 「ドキュメントを同期して」 |
| Skill | `gh-actions-check` | GitHub Actions の状態確認と失敗原因の特定 | 「CIの状態を見て」 |
| Skill | `infra-incident` | 障害報告書を決まった形式で作成する | 「障害報告書の草案を作って」 |
| Skill | `repo-security` | セキュリティ点検と、コミット時の自動チェック（pre-commit フック）導入 | 「セキュリティチェックして」 |
| Agent | `security-auditor` / `code-architect` / `test-generator` | 監査・設計・テスト作成を任せる専門のサブエージェント | 「security-auditor で監査して」 |
| 設定 | 機密ファイル読み取り禁止 | `.env`・`~/.ssh` などを Claude が読めないようにする | （自動） |
| 設定 | 起動時リマインド | 7 日以上セキュリティ点検をしていないと通知する | （自動） |
| 設定 | ステータスライン | 画面下部にフォルダ・ブランチ・モデル・使用率を表示する | （自動） |
| ルール | `CLAUDE.md` | 作業手順（7 段階）・Git ルール・セキュリティ方針 | （自動） |

**用語メモ**
- **Skill（スキル）**: Claude Code に「この種の作業はこの手順でやる」と教える説明書。`~/.claude/skills/<名前>/SKILL.md` に置くと有効になる
- **`~/.claude`**: Claude Code の個人設定フォルダ。`~` はホームフォルダ（例: `/home/<ユーザー名>`）の略
- **フック（hook）**: 決まったタイミング（起動時など）に自動で実行されるコマンド

---

## 1. 事前準備

### 1-1. 必要なもの

ターミナルで次を実行し、バージョンが表示されれば OK です。

```bash
claude --version     # Claude Code（必須）
python3 --version    # 3.10 以上（codegraph Skill に必要）
git --version        # 必須（pre-commit フックは Git の機能）
jq --version         # 任意: ステータスライン表示に必要
gh --version         # 任意: gh-actions-check Skill に必要
```

足りないものは、Ubuntu / WSL なら `sudo apt install python3 git jq`、macOS なら `brew install python git jq` で入ります。

### 1-2. キットのファイルを用意する

次のどちらかで、キットのフォルダを手元に用意します。

**方法 A: メール添付の ZIP を使う**

```bash
mkdir -p ~/Project && cd ~/Project
unzip ~/Downloads/claude-portable-kit.zip -d claude-portable-kit   # 保存場所に合わせて変更
cd claude-portable-kit
```

> WSL で Windows の「ダウンロード」フォルダにある場合は `/mnt/c/Users/<Windowsのユーザー名>/Downloads/` です。

**方法 B: GitHub から取得する**

```bash
mkdir -p ~/Project && cd ~/Project
git clone https://github.com/7hay/claude-portable-kit.git
cd claude-portable-kit
```

以降のコマンドは、すべて **このキットのフォルダ（`claude-portable-kit`）の中で** 実行します。
`ls` で `claude`・`README.md`・`MANUAL_INSTALL.md` が見えれば正しい場所です。

### 1-3. 今の設定をバックアップする（必須）

**なぜ**: 手作業ではうっかり上書きしがちです。元に戻せる状態を先に作ります。

```bash
mkdir -p ~/.claude
cp -a ~/.claude ~/claude-backup-$(date +%Y%m%d)
ls -d ~/claude-backup-*        # バックアップができたことを確認
```

---

## 2. Skill をコピーする

```bash
mkdir -p ~/.claude/skills
ls ~/.claude/skills            # 既にある Skill を確認
```

同じ名前のフォルダ（`codegraph` など）が **既にある場合**は、上書きしてよいか中身を見て判断してください。
問題なければコピーします。

```bash
cp -r claude/skills/* ~/.claude/skills/
chmod +x ~/.claude/skills/*/scripts/*
```

- `cp -r` = フォルダごとコピー
- `chmod +x` = スクリプトに「実行してよい」という権限を付ける（付けないと動かない）

一部の Skill だけ入れたい場合は、`cp -r claude/skills/doc-audit ~/.claude/skills/` のように 1 つずつコピーします。

---

## 3. サブエージェントをコピーする

```bash
mkdir -p ~/.claude/agents
ls ~/.claude/agents            # 同名ファイルがあれば中身を確認
cp claude/agents/*.md ~/.claude/agents/
```

---

## 4. フック用スクリプトをコピーする

```bash
mkdir -p ~/.claude/hooks
cp claude/hooks/*.sh ~/.claude/hooks/
chmod +x ~/.claude/hooks/*.sh
```

---

## 5. settings.json を設定する（いちばん注意が必要）

`~/.claude/settings.json` は Claude Code の動作設定ファイルです。**書式（JSON）が 1 文字でも崩れると設定全体が読み込まれなくなる**ため、
編集後に必ず 5-3 の確認をしてください。

まず、ファイルがあるか確認します。

```bash
ls ~/.claude/settings.json
```

### 5-1. ファイルが「無い」場合

テンプレートの `__CLAUDE_HOME__` を、実際のフォルダの場所に置き換えて作成します。

```bash
sed "s#__CLAUDE_HOME__#$HOME/.claude#g" claude/settings.template.json > ~/.claude/settings.json
```

- `sed "s#A#B#g"` = ファイル中の A をすべて B に置き換える命令
- `$HOME` = ホームフォルダの場所に自動で置き換わる

### 5-2. ファイルが「既にある」場合

**上書きしてはいけません**（モデル設定や他の許可設定が消えます）。エディタで開き、次の 3 か所を **追加** します。

```bash
code ~/.claude/settings.json    # VS Code。nano ~/.claude/settings.json でも可
```

**(1) 機密ファイルの読み取り禁止** — `"permissions"` の中の `"deny"` に追加（既にある行は重複させない）

```json
"permissions": {
  "deny": [
    "Read(~/.secrets)",
    "Read(**/.env)",
    "Read(**/.env.*)",
    "Read(~/.ssh/**)",
    "Read(~/.aws/**)",
    "Read(**/credentials*)",
    "Read(**/secrets*)"
  ]
}
```

**(2) 起動時リマインド** — `"hooks"` の中に `"SessionStart"` を追加（既に `SessionStart` があれば、その配列に `{ ... }` を 1 つ足す）

```json
"hooks": {
  "SessionStart": [
    {
      "hooks": [
        {
          "type": "command",
          "command": "bash /home/<ユーザー名>/.claude/hooks/security-remind.sh",
          "timeout": 5
        }
      ]
    }
  ]
}
```

**(3) ステータスライン** — `"statusLine"` が **まだ無い場合だけ** 追加（既にあれば自分の設定を優先）

```json
"statusLine": {
  "type": "command",
  "command": "bash /home/<ユーザー名>/.claude/hooks/statusline-command.sh"
}
```

> `/home/<ユーザー名>` は `echo $HOME` の結果に置き換えます（macOS なら `/Users/<ユーザー名>`）。
> JSON の注意: 項目の区切りには `,`（カンマ）が必要で、最後の項目の後ろには `,` を付けません。

### 5-3. 書式チェック（必須）

```bash
python3 -m json.tool ~/.claude/settings.json > /dev/null && echo "OK: 書式は正しい"
```

エラーが出たら、表示された行番号付近のカンマや括弧を直します。直せない場合は 1-3 のバックアップから戻してやり直してください。

---

## 6. CLAUDE.md（開発ルール）を設定する

```bash
ls ~/.claude/CLAUDE.md
```

**無い場合**: そのままコピーし、末尾の「この環境について」に OS やプロジェクトの場所などを書き足します。

```bash
cp claude/CLAUDE.template.md ~/.claude/CLAUDE.md
```

**既にある場合**: 上書きせず、横に置いて見比べ、必要な節（Work Process・Git Rules・Security Policy など）だけを自分の CLAUDE.md にコピーします。

```bash
cp claude/CLAUDE.template.md ~/.claude/CLAUDE.portable.md
code ~/.claude/CLAUDE.md ~/.claude/CLAUDE.portable.md
```

> テンプレートは「日本語で、初心者向けに理由も添えて説明する」設定になっています。
> 不要なら先頭の「Response Language & Style」を書き換えてください。

---

## 7. 動作確認

1. **Claude Code を再起動する**（VS Code ならコマンドパレットで「Developer: Reload Window」）
   — 設定は起動時に読み込まれるため、再起動しないと反映されません
2. 起動直後に「⚠️ セキュリティチェック未実行」と表示されれば、**起動時リマインドは成功**
3. チャットで次を確認する

| 確認すること | 方法 | 期待結果 |
|---|---|---|
| Skill | `/skills` と入力 | 6 つの Skill が一覧に出る |
| Agent | `/agents` と入力 | 3 つのエージェントが出る |
| 読み取り禁止 | 「`~/.ssh` の中身を読んで」と頼む | 拒否される |
| Skill の実行 | 作業中のリポジトリで「セキュリティチェックして」 | 点検結果が表示され、以後リマインドが消える |
| ステータスライン | 画面下部を見る | `ユーザー名:フォルダ (ブランチ) \| モデル名 \| Ctx:xx%` |

ターミナルから直接確かめることもできます。

```bash
ls ~/.claude/skills/*/SKILL.md                                   # 6 件表示される
bash ~/.claude/skills/repo-security/scripts/claude-security-check.sh ~/Project/<任意のリポジトリ>
```

---

## 8. リポジトリごとの設定（作業するリポジトリそれぞれで 1 回）

コミット時に API キーの混入などを自動で止める **pre-commit フック** を入れます。
`.git/hooks/` は Git で共有されない（clone しても配られない）ため、**リポジトリごとに** 必要です。

```bash
cd ~/Project/<対象リポジトリ>
ls .git/hooks/pre-commit 2>/dev/null && echo "既にフックあり: 中身を確認してから判断"
cp ~/.claude/skills/repo-security/scripts/pre-commit.sh .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

Claude Code に「このリポジトリに pre-commit を入れて」と頼んでも同じことをしてくれます。

---

## 9. よくあるトラブル

| 症状 | 原因と対処 |
|---|---|
| `/skills` に出てこない | 再起動していない／`SKILL.md` の場所が `~/.claude/skills/<名前>/SKILL.md` になっていない |
| 設定が全部効かなくなった | settings.json の書式崩れ。5-3 のチェックを実行し、だめならバックアップから戻す |
| 起動時リマインドが出ない | settings.json のフックのパスが違う。`ls` でパスを確認し、`<ユーザー名>` の置き換え漏れがないか見る |
| `Permission denied` | `chmod +x` を忘れている（手順 2・4） |
| ステータスラインが空 | `jq` が未インストール |
| `gh: command not found` | gh CLI を入れて `gh auth login` |
| ZIP を展開したらスクリプトが動かない | Windows 経由で改行コードが変わった可能性。`sed -i 's/\r$//' ~/.claude/hooks/*.sh ~/.claude/skills/*/scripts/*.sh` |

---

## 10. 元に戻す（アンインストール）

```bash
rm -r ~/.claude/skills/{codegraph,doc-audit,doc-sync,gh-actions-check,infra-incident,repo-security}
rm ~/.claude/agents/{code-architect,security-auditor,test-generator}.md
rm ~/.claude/hooks/{security-remind,statusline-command}.sh
```

その後、settings.json から手順 5 で追加した部分を削除します。
丸ごと元に戻したい場合は、手順 1-3 のバックアップ（`~/claude-backup-YYYYMMDD`）から必要なファイルをコピーし直します。

---

## 付録 A: Windows ネイティブ（WSL を使わない）の場合

- 設定フォルダは `C:\Users\<ユーザー名>\.claude\`（エクスプローラーで `%USERPROFILE%\.claude` と入力すると開く）
- Skill（手順 2）・Agent（手順 3）・CLAUDE.md（手順 6）は、エクスプローラーでフォルダごとコピーするだけで使えます
- フックとステータスライン（手順 4・5）、`repo-security` のスクリプトは **bash 用** のため、
  Git for Windows（Git Bash）が必要です。settings.json のパスは `bash C:/Users/<ユーザー名>/.claude/hooks/security-remind.sh` のように
  `/`（スラッシュ）区切りで書きます
- うまく動かない場合は、フック部分（手順 4・5 の (2)(3)）を省略しても Skill・Agent・読み取り禁止は利用できます
