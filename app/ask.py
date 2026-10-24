"""第1回: 素のLLMに1回だけ質問するスクリプト。

使い方:
    uv run python -m app.ask "LoRAとは何ですか？"
    uv run python -m app.ask            # 質問を省略すると、講座に固有の質問をする

ツールも会話履歴も持たない「素の」呼び出し。
講座に固有のことを聞くと、「分からない」と答えるか、一般論でもっともらしく答える
（講座の実際とは違う）ことを確かめよう。
（第3回で、用語集を検索できるエージェントにして改善する）
"""

import argparse
from dataclasses import dataclass
from time import perf_counter

import httpx
from google import genai
from google.genai import errors, types

from app.config import MODEL, api_error_message, get_api_key

# 講座に固有の質問。正しい答えは data/glossary.json の homework-levels にある
DEFAULT_QUESTION = "AIE2026の講座の宿題にある「3レベル」とは何ですか？"


@dataclass(frozen=True)
class Measurement:
    """1回のAPI応答。取得できなかったトークン数は0にせずNoneで残す。"""

    text: str
    elapsed_seconds: float
    input_tokens: int | None
    output_tokens: int | None
    thoughts_tokens: int | None
    total_tokens: int | None
    cached_tokens: int | None
    finish_reason: str | None
    model_version: str | None


def create_client() -> genai.Client:
    # 暗黙の再試行による待ち時間を、モデルの応答時間と混同しないようにする。
    return genai.Client(
        api_key=get_api_key(),
        http_options=types.HttpOptions(
            timeout=120_000,
            retry_options=types.HttpRetryOptions(attempts=1),
        ),
    )


def measure(
    client: genai.Client,
    question: str,
    *,
    model: str = MODEL,
    temperature: float = 1.0,
    max_output_tokens: int = 2048,
) -> Measurement:
    """送信直前から応答全体の受信までを計測する（TTFTではない）。"""
    config = types.GenerateContentConfig(
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        # SDKによる続きを求める追加リクエストも無効化し、1計測=1リクエストにする。
        automatic_continuation=False,
    )
    start = perf_counter()
    response = client.models.generate_content(model=model, contents=question, config=config)
    elapsed = perf_counter() - start
    usage = response.usage_metadata
    candidate = response.candidates[0] if response.candidates else None
    reason = candidate.finish_reason if candidate else None
    return Measurement(
        text=response.text or "",
        elapsed_seconds=elapsed,
        input_tokens=usage.prompt_token_count if usage else None,
        output_tokens=usage.candidates_token_count if usage else None,
        thoughts_tokens=usage.thoughts_token_count if usage else None,
        total_tokens=usage.total_token_count if usage else None,
        cached_tokens=usage.cached_content_token_count if usage else None,
        finish_reason=reason.value if reason else None,
        model_version=response.model_version,
    )


def format_metrics(result: Measurement) -> str:
    def token(value: int | None) -> str:
        return str(value) if value is not None else "未取得"

    return (
        f"[応答時間] {result.elapsed_seconds:.3f} 秒\n"
        f"[トークン] 入力={token(result.input_tokens)} / 出力={token(result.output_tokens)} / "
        f"思考={token(result.thoughts_tokens)} / 合計={token(result.total_tokens)}\n"
        f"[キャッシュ済み入力] {token(result.cached_tokens)}\n"
        f"[終了理由] {result.finish_reason or '未取得'}"
    )


def ask(question: str) -> str:
    with create_client() as client:
        result = measure(client, question)
    print(format_metrics(result))
    return result.text or "テキスト回答がありません。終了理由を確認してください。"


def main() -> None:
    parser = argparse.ArgumentParser(description="素のLLMに質問する")
    parser.add_argument("question", nargs="?", default=DEFAULT_QUESTION)
    args = parser.parse_args()

    print(f"[model] {MODEL}")
    print(f"[質問] {args.question}\n")
    try:
        print(ask(args.question))
    except errors.APIError as e:
        # SDKのエラー本文にはリクエスト情報が含まれ得るため、そのまま表示しない。
        print(api_error_message(e.code))
        raise SystemExit(1)
    except httpx.HTTPError:
        print("通信に失敗しました。ネットワーク接続とタイムアウトを確認してください。")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
