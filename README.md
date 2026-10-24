# AIE2026 演習・宿題リポジトリ

AIエンジニアリング実践講座（AIE2026）の演習と宿題で使うリポジトリです。
講座を通して、**AIエンジニアリングの学習を支援するエージェント**を少しずつ育てていきます。

## 想定する環境

演習は **ブラウザだけで** 進められるように作っています。自分の PC への導入は不要です。

| 使うもの | 用途 | 注意 |
|---|---|---|
| GitHub の **個人** アカウント | このリポジトリを fork し、作業ブランチと PR で提出する | 会社や学校が管理するアカウントでは Codespaces・Copilot が制限されることがあります |
| GitHub Codespaces | 第1・3・5回などの開発環境。`.devcontainer/` の設定で Python 3.12・uv・Node.js が入ったコンテナが自動で用意されます | 個人アカウントの無料枠は月 120 コア時間（2 コアで約 60 時間）。**使い終わったら停止**してください |
| GitHub Copilot（Free でよい） | コードの補完とチャット。第5回の発展課題では MCP クライアントとしても使います | Free は補完・チャットの回数に月の上限があります |
| Gemini API（Google AI Studio の無料枠） | LLM の呼び出し。**個人**の Google アカウントでキーを発行し、Codespaces secret `GEMINI_API_KEY` で渡します | 無料枠には 1 分あたり・1 日あたりの上限があります（下の「前提と制約」） |
| Google Colab（T4 GPU、無料枠） | 第2回の LoRA 学習だけに使います | GPU の利用時間に上限があります。終わったらランタイムを削除してください |

自分の PC で動かす場合は、Python 3.12 と [uv](https://docs.astral.sh/uv/) を入れて `uv sync --frozen` を実行し、環境変数 `GEMINI_API_KEY` を設定してください。

## はじめに（第1回）

1. このリポジトリを自分のアカウントに **fork** する
2. [Google AI Studio](https://aistudio.google.com/apikey) で Gemini API キーを作る
3. GitHub の **Settings → Codespaces → Secrets** に `GEMINI_API_KEY` を登録し、使う repository に自分の fork を選ぶ
4. 自分の fork で **Code → Codespaces → Create codespace on main**
5. ターミナルで動作確認

```bash
uv run pytest -q
uv run python -m app.ask "LoRAとは何ですか？"
```

詳しい手順は [lectures/01/problem.md](lectures/01/problem.md) を見てください。

## 第1回の発展課題をローカルPCで実行する

1. リポジトリ直下の `.env` を開き、`GEMINI_API_KEY=` の右側に取得済みのキーを入力して保存します。別の環境では `.env.example` を `.env` にコピーしてください。`.env` は Git の管理対象外です。
2. [Google AI Studio](https://aistudio.google.com/) で、使用するプロジェクトのモデル別の利用枠・料金区分を確認します。既定の比較対象は `gemini-3.5-flash-lite` と `gemini-3.1-flash-lite` です。利用できるモデルはプロジェクトによって異なります。
3. リポジトリ直下のターミナルで実行します。

```bash
# 初回のみ: 固定済みの依存パッケージをインストール
uv sync --frozen

# 実行計画の確認。APIキー不要で、通信も行わない
uv run python -m app.benchmark --dry-run

# 2モデル × 3質問 × 各3回 = 最大18回。通常は数分かかる
uv run --env-file .env python -m app.benchmark
```

完了後に表示される `lectures/01/results/<実行日時>/summary.md` に比較表ができます。同じフォルダの `results.jsonl` に回答全文と各回の数値、`run.json` に実験条件を保存します。比較表と講座固有の質問への回答を [answer.md](lectures/01/answer.md) に転記し、実測に基づく考察を追記してください。

質問を変更する場所は `app/benchmark.py` の `QUESTIONS` です。モデル・開始間隔なども指定できます。

```bash
uv run --env-file .env python -m app.benchmark \
  --models gemini-3.5-flash-lite gemini-3.1-flash-lite \
  --repeats 3 --interval 30 --temperature 1.0 --max-output-tokens 2048

# 1つの質問だけ試す場合（この呼び出しも利用枠を消費する）
uv run --env-file .env python -m app.ask "LoRAとは何ですか？"
```

既定の開始間隔は最低15秒で、無料枠内で実行できることを保証する設定ではありません。429・通信エラーなどでは途中までの結果を保存して停止します。上限は [公式のレート制限の説明](https://ai.google.dev/gemini-api/docs/rate-limits) と AI Studio で確認してください。日単位の上限や利用枠が0の場合、1分待つだけでは解消しません。

`MAX_TOKENS`・空回答などの未完了応答は保存しますが、完了応答の平均には含めません。出力上限を増やす場合は、両モデルを同じ条件で再測定します。Ctrl+C でも受信済みの結果を保存します。再実行は別フォルダに保存され、過去の結果を上書きしません。

Codespaces secret が設定済みなら、`--env-file .env` は不要です。

## 構成

```
.devcontainer/   Codespaces の環境定義（Python 3.12、uv、Node.js。起動時に uv sync --frozen）
.github/workflows/test.yml  PR ごとにテストを実行（fork では Actions タブで有効化が必要）
app/
  config.py      モデル名とAPIキーの読み込み
  ask.py         第1回：LLMに質問する
  tools.py       第3回：エージェントのツール（用語集の検索など）
  agent.py       第3回：Pydantic AI の学習支援エージェント（第5回：--mcp で MCP 経由）
  mcp_server.py  第5回：用語集を公開する MCP サーバー
  mcp_servers.json 第5回：使う MCP サーバーの設定（mcpServers 形式）
data/
  glossary.json  講座の用語集
  lectures/      各回の要点
lectures/NN/
  problem.md     その回の演習と宿題
  answer.md      あなたが記入して提出するファイル
notebooks/       第2回：Google Colab で動かす LoRA のノートブック（lora_format_tuning.ipynb）
scripts/         補助スクリプト
tests/           テスト（APIキー不要）
pyproject.toml / uv.lock  依存パッケージとその固定版
```

## 提出のしかた

1. 回ごとに作業ブランチを作る（例：`git switch -c lec01`）
2. 演習・宿題を行い、`lectures/NN/answer.md` に記入する
3. push して、**自分の fork の中で** 作業ブランチ → `main` の PR を作る

宿題は「基礎・実装・発展」の3レベルがあり、どれか1つに取り組めば完了です。

## 前提と制約

- **依存パッケージの版は固定**しています（`uv.lock`。Python 3.12、pydantic-ai-slim 2.57.0、google-genai 2.31.0）。講座の期間中は上げません。`uv sync --frozen` でそのまま入れてください。
- **既定のモデルは `gemini-3.5-flash-lite`** です。環境変数 `AIE_MODEL` で切り替えられます（下の「モデルの切り替え」）。ほかのモデルや自前契約の API を使ってもかまいません
- **Gemini API の無料枠にはレート制限**があります。エージェント（第3回以降）は 1 つの質問で LLM を複数回呼ぶので、第1回より早く上限に達します。429が出たら AI Studio で利用枠を確認し、分単位なら間隔を空け、日単位ならリセットを待ってください。`モデルが混み合っています（503）` が続くときは `AIE_MODEL=gemini-3.1-flash-lite` を試してください
- **API キーは環境変数 `GEMINI_API_KEY` だけ**で渡します。コード・コミット・チャットに貼らないでください。漏れたら AI Studio で削除して作り直します
- Codespaces からインターネットへは出られますが、外から Codespaces の中へは接続できません（ポート転送は既定で非公開）。第5回の MCP サーバーは Codespaces の中で動かします
- テスト（`uv run pytest -q`）は API キーなしで動きます（LLM を呼ばない TestModel を使用）

## 守ってほしいこと

- **APIキーをコードやコミットに書かない。** Codespaces secret、または Git 管理対象外のローカル `.env` から環境変数として渡します
- **使い終わったら Codespaces を停止する。** 無料枠を使い切ると起動できなくなります
- AIツール（Copilot など）は使ってかまいません。提案されたコードは、読んで理解してから採用してください

## モデルの切り替え

既定モデルは `gemini-3.5-flash-lite` です。環境変数 `AIE_MODEL` で切り替えられます。

```bash
AIE_MODEL=gemini-3.5-flash uv run python -m app.ask "LoRAとは何ですか？"
```

無料枠には1分あたり・1日あたりのリクエスト上限があります。上限は [Gemini API のレート制限のページ](https://ai.google.dev/gemini-api/docs/rate-limits) で確認してください。
