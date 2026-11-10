---
name: codegraph
description: Build a code knowledge graph (CODEMAP.md) for a Python/JS/TS/Rust codebase — God Nodes, Blast Radius, clusters, per-module summary — so the whole structure can be grasped without rereading every source file. Use before exploring an unfamiliar codebase, or when asked 「コードグラフを作って」「codegraph」「CODEMAPを更新して」.
---

# Codegraph（コードのナレッジグラフ生成）

## 目的

コードベースを解析し、コードの「地図」= `CODEMAP.md` を生成する。
会話のたびに全ソースを読み直す代わりに地図を読むことで、トークン消費を抑えつつ
根幹ファイル・変更の影響範囲・モジュール構成を把握する。

## 実行手順

```bash
python3 ~/.claude/skills/codegraph/scripts/codegraph.py --src <プロジェクトのパス> [--out <出力先>]
# --out 省略時は <src>/.codegraph/CODEMAP.md
```

依存ライブラリ不要（Python 3.10+ 標準ライブラリのみ）。
`.codegraph/` は生成物なので、対象リポジトリの `.gitignore` に追加するか確認する。

| 言語 | 拡張子 | import 解析 | 内部エッジの根拠 |
|---|---|---|---|
| Python | `.py` | `ast` | 相対/絶対 import の解決 |
| JS/TS | `.js/.jsx/.ts/.tsx/.mjs/.cjs` | 正規表現 | 相対パス import |
| Rust | `.rs` | 正規表現 | `mod foo;` |

## CODEMAP.md の内容

| セクション | 内容 |
|---|---|
| God Nodes | 被 import 数の多い根幹モジュール上位10（壊すと影響大） |
| Blast Radius | 各モジュール変更時に影響が波及する範囲 |
| クラスタ | import で繋がったモジュール群 |
| 外部依存 / 未解決 import | 内部=Fact / 外部=External / 解決不能=Guess |
| モジュール別サマリー | docstring・クラス・関数・import・LOC |

## 複数プロジェクト横断（Shared Brain）

```bash
python3 ~/.claude/skills/codegraph/scripts/codegraph_registry.py --base ~/Project
# 出力: ~/.claude/registry/REGISTRY.md + <project>/CODEMAP.md
# 既定値は環境変数 CODEGRAPH_BASE / CODEGRAPH_REGISTRY でも変更可
```

会話開始時は `REGISTRY.md` → 該当プロジェクトの `CODEMAP.md` → 必要なファイルだけ Read、の順で読む。

## 確認ポイント

- `Found N files` の数が想定どおりか（`.venv`/`node_modules` 等は自動除外）
- God Nodes が直感に合うか
- 「未解決 import（Guess）」は解決失敗の候補として要確認

## 既知の制約

- JS/TS は相対パス import のみ（`tsconfig` paths 未対応）
- Rust は `mod` 宣言ベース（`use crate::...` のファイル解決は未対応）
