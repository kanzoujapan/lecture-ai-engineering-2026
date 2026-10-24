"""第1回・発展: モデルと質問を変え、応答時間とトークン数を比較する。

    uv run --env-file .env python -m app.benchmark --dry-run
    uv run --env-file .env python -m app.benchmark

質問を変える場合は QUESTIONS を編集する。実際に送った質問も結果に保存する。
"""

import argparse
from dataclasses import asdict
from datetime import datetime
from importlib.metadata import version
import json
import math
from pathlib import Path
import random
from statistics import mean, median
import time

import httpx
from google import genai
from google.genai import errors

from app.ask import DEFAULT_QUESTION, create_client, measure
from app.config import DEFAULT_MODEL, api_error_message

QUESTIONS = {
    "short": "LoRAとは何ですか？日本語で100文字程度で説明してください。",
    "detailed": (
        "LoRAとフルファインチューニングを、更新するパラメータ、GPUメモリ、"
        "用途の3点で比較してください。日本語で400文字程度で説明してください。"
    ),
    "course": DEFAULT_QUESTION,
}
RESULTS_DIR = Path(__file__).resolve().parents[1] / "lectures" / "01" / "results"
ORDER_SEED = 42


def summary_markdown(records: list[dict], models: list[str], repeats: int) -> str:
    """完了した回答だけを比較する。失敗を0秒・0トークンとして平均しない。"""
    planned = len(models) * len(QUESTIONS) * repeats
    lines = [
        "# 第1回 発展課題・実測結果",
        "",
        f"- 試行済み: {len(records)} / {planned} 回",
        f"- 完了: {sum(r['status'] == 'ok' for r in records)} 回",
        "- 設定・質問・実行日時: [run.json](run.json)",
        "- 各回の回答・計測値・エラー: [results.jsonl](results.jsonl)",
        "- 時間は送信から全応答受信まで。待機時間・クライアント作成は含まない。",
        "- STOPで終了し、テキストがある回答だけを集計。未完了・エラーは平均から除外。",
        "- トークン未取得値は0に置き換えず、取得できた値のみで平均する。",
        "",
        "## 応答時間",
        "",
        "| モデル | 質問 | 完了/予定 | 未完了 | エラー | うち429 | 平均秒 | 中央値秒 | 最小〜最大秒 |",
        "|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    token_lines = [
        "", "## トークン数の平均", "",
        "各セルは平均（取得できた回数/完了回数）。キャッシュは入力の内数。",
        "",
        "| モデル | 質問 | 入力 | 出力 | 思考 | 合計 | キャッシュ |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for model in models:
        for question_id in QUESTIONS:
            group = [r for r in records if r['model'] == model and r['question_id'] == question_id]
            complete = [r for r in group if r['status'] == 'ok']
            elapsed = [r['elapsed_seconds'] for r in complete]
            times = (
                f"{mean(elapsed):.3f} | {median(elapsed):.3f} | {min(elapsed):.3f}〜{max(elapsed):.3f}"
                if elapsed else "— | — | —"
            )
            lines.append(
                f"| {model} | {question_id} | {len(complete)}/{repeats} | "
                f"{sum(r['status'] == 'incomplete' for r in group)} | "
                f"{sum(r['status'] not in ('ok', 'incomplete') for r in group)} | "
                f"{sum(r.get('error_code') == 429 for r in group)} | {times} |"
            )
            values = []
            for field in ('input_tokens', 'output_tokens', 'thoughts_tokens', 'total_tokens', 'cached_tokens'):
                available = [r[field] for r in complete if r[field] is not None]
                values.append(
                    f"{mean(available):.1f} ({len(available)}/{len(complete)})"
                    if available else "—"
                )
            token_lines.append(f"| {model} | {question_id} | " + " | ".join(values) + " |")
    lines.extend(token_lines)
    lines.extend(["", "## 講座固有の質問への回答（各モデルの最初の完了応答）", ""])
    for model in models:
        first = next((r for r in records if r['model'] == model and r['question_id'] == 'course' and r['status'] == 'ok'), None)
        lines.extend([f"### {model}", ""])
        if first:
            lines.extend("> " + line for line in first['text'].splitlines())
            lines.extend(["", f"入力: {first['input_tokens']} / 出力: {first['output_tokens']}", ""])
        else:
            lines.extend(["完了した回答はありません。", ""])
    return "\n".join(lines) + "\n"


def run_benchmark(
    client: genai.Client,
    models: list[str],
    output_dir: Path,
    *,
    repeats: int = 3,
    interval_seconds: float = 15.0,
    temperature: float = 1.0,
    max_output_tokens: int = 2048,
) -> list[dict]:
    output_dir.mkdir(parents=True, exist_ok=False)
    jobs = [(model, qid, repeat) for repeat in range(1, repeats + 1) for qid in QUESTIONS for model in models]
    random.Random(ORDER_SEED).shuffle(jobs)
    settings = {
        "started_at": datetime.now().astimezone().isoformat(),
        "sdk_version": version("google-genai"),
        "models": models, "questions": QUESTIONS, "repeats": repeats,
        "temperature": temperature, "max_output_tokens": max_output_tokens,
        "thinking_config": "model_default", "retry_attempts": 1,
        "automatic_continuation": False,
        "http_timeout_ms": 120_000, "interval_seconds": interval_seconds,
        "order_seed": ORDER_SEED, "planned_requests": len(jobs),
    }
    (output_dir / "run.json").write_text(json.dumps(settings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    records = []
    previous_start = None
    try:
        with (output_dir / "results.jsonl").open("w", encoding="utf-8") as log:
            for index, (model, question_id, repeat) in enumerate(jobs, 1):
                if previous_start is not None:
                    wait = max(0.0, interval_seconds - (time.perf_counter() - previous_start))
                    if wait:
                        time.sleep(wait)
                print(f"[{index}/{len(jobs)}] {model} / {question_id} / {repeat}回目", flush=True)
                record = {
                    "request_index": index, "model": model, "question_id": question_id,
                    "question": QUESTIONS[question_id], "repeat": repeat,
                    "started_at": datetime.now().astimezone().isoformat(),
                }
                previous_start = time.perf_counter()
                try:
                    result = measure(
                        client, QUESTIONS[question_id], model=model,
                        temperature=temperature, max_output_tokens=max_output_tokens,
                    )
                    record.update(asdict(result))
                    record['status'] = 'ok' if result.text.strip() and result.finish_reason == 'STOP' else 'incomplete'
                except errors.APIError as error:
                    record.update(status="api_error", error_code=error.code, error=api_error_message(error.code))
                except httpx.HTTPError:
                    record.update(status="network_error", error="通信エラー。接続とタイムアウトを確認してください。")
                except KeyboardInterrupt:
                    record.update(status="interrupted", error="利用者が中断しました。")
                if 'elapsed_seconds' not in record:
                    record['elapsed_seconds'] = time.perf_counter() - previous_start
                records.append(record)
                log.write(json.dumps(record, ensure_ascii=False) + "\n")
                log.flush()  # 途中で止めても、受信済みの結果を残す。
                print(f"  {record['status']} / {record['elapsed_seconds']:.3f} 秒", flush=True)
                if record['status'] not in ('ok', 'incomplete'):
                    print(record['error'])
                    print("追加のリクエストを停止しました。保存した結果と利用枠を確認してください。")
                    break
    except KeyboardInterrupt:
        print("待機中に中断しました。受信済みの結果を保存します。")
    finally:
        (output_dir / "summary.md").write_text(summary_markdown(records, models, repeats), encoding="utf-8")
        print(f"比較表: {output_dir / 'summary.md'}")
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description="第1回 発展課題: 応答時間・トークン数の比較")
    parser.add_argument("--models", nargs="+", default=[DEFAULT_MODEL, "gemini-3.1-flash-lite"])
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--interval", type=float, default=15.0, help="リクエスト開始間隔の最小秒数（既定: 15）")
    parser.add_argument("--temperature", type=float, default=1.0)
    parser.add_argument("--max-output-tokens", type=int, default=2048)
    parser.add_argument("--output-dir", type=Path, help="未作成の保存先。省略時は日時別フォルダを作成")
    parser.add_argument("--dry-run", action="store_true", help="計画だけ表示する（APIキー不要・通信なし）")
    args = parser.parse_args()
    if args.repeats < 1 or args.max_output_tokens < 1:
        parser.error("--repeats と --max-output-tokens は1以上にしてください。")
    if not math.isfinite(args.interval) or args.interval < 0:
        parser.error("--interval は0以上の有限の数にしてください。")
    if not 0 <= args.temperature <= 2:
        parser.error("--temperature は0以上2以下にしてください。")
    models = list(dict.fromkeys(args.models))
    planned = len(models) * len(QUESTIONS) * args.repeats
    output_dir = args.output_dir or RESULTS_DIR / datetime.now().astimezone().strftime("%Y%m%d-%H%M%S-%f")
    if output_dir.exists():
        parser.error("保存先が存在します。過去の結果を守るため、新しいフォルダを指定してください。")
    print(f"{len(models)}モデル × {len(QUESTIONS)}質問 × {args.repeats}回 = 最大{planned}リクエスト")
    print(f"モデル: {', '.join(models)}")
    print(f"開始間隔: {args.interval}秒以上 / temperature: {args.temperature} / 出力上限: {args.max_output_tokens}")
    print(f"保存先: {output_dir}")
    if args.dry_run:
        for question_id, question in QUESTIONS.items():
            print(f"{question_id}: {question}")
        return
    with create_client() as client:
        records = run_benchmark(
            client, models, output_dir, repeats=args.repeats, interval_seconds=args.interval,
            temperature=args.temperature, max_output_tokens=args.max_output_tokens,
        )
    if len(records) != planned or any(r['status'] != 'ok' for r in records):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
