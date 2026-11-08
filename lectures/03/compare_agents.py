"""第3回: 同じ質問への回答とツール呼び出しを保存する実験用スクリプト。

リポジトリ直下で実行する。APIキーは環境変数から読み、結果には保存しない。
PYTHONPATH=. uv run --frozen --env-file .env --with google-adk==2.14.0 \
    python lectures/03/compare_agents.py
"""

import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import random
import subprocess
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from app.agent import INSTRUCTIONS, agent, build_model, print_trace
from app.ask import DEFAULT_QUESTION, ask
from app.config import MODEL
from pydantic_ai.messages import ToolCallPart, ToolReturnPart
from pydantic_ai.usage import UsageLimits

ROOT = Path(__file__).resolve().parents[2]
QUESTIONS = {
    "levels": DEFAULT_QUESTION,
    "tag": "AIE2026の講座で使う「lecNN-start タグ」とは何ですか？",
    "lora": "LoRAとQLoRAの違いは？",
    "summary": "第3回では何を学びますか？",
    "quiz": "第2回の内容から確認問題を1問出して",
    "unknown": "AIE2026の講座で使う「ニューラル・パスポート」とは何ですか？",
}


def save_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_pydantic(question, raw_path):
    result = agent.run_sync(question, model=build_model(), usage_limits=UsageLimits(request_limit=6))
    raw_path.write_bytes(result.all_messages_json())
    calls, returns = [], []
    for message in result.all_messages():
        for part in message.parts:
            if isinstance(part, ToolCallPart):
                calls.append({"name": part.tool_name, "args": part.args_as_dict()})
            elif isinstance(part, ToolReturnPart):
                returns.append({"name": part.tool_name, "content": part.content})
    print_trace(result)
    return {
        "answer": result.output,
        "tool_calls": calls,
        "tool_returns": returns,
        "requests": result.usage.requests,
        "input_tokens": result.usage.input_tokens,
        "output_tokens": result.usage.output_tokens,
    }


def run_adk(question, raw_path):
    completed = subprocess.run(
        ["adk", "run", "--in_memory", "--jsonl", "--timeout", "60s",
         "adk_agent/glossary_agent", question],
        cwd=ROOT, capture_output=True, text=True, timeout=90, check=False,
    )
    raw_path.write_text(completed.stdout, encoding="utf-8")
    if completed.stderr.strip():
        raw_path.with_suffix(".stderr.txt").write_text(completed.stderr, encoding="utf-8")
    if completed.returncode:
        raise RuntimeError(f"adk run failed: exit {completed.returncode}; see {raw_path.name}")
    return summarize_adk_output(completed.stdout)


def summarize_adk_output(stdout):
    # ADK 2.14.0は--jsonlでも冒頭にログファイルの案内を出す。原文はそのまま保存する。
    events = [json.loads(line) for line in stdout.splitlines() if line.lstrip().startswith("{")]
    if not events:
        raise ValueError("ADKのイベントがありません。")
    calls, returns, answers, usage = [], [], [], []
    for event in events:
        content = event.get("content", {})
        for part in content.get("parts", []):
            if "functionCall" in part:
                call = part["functionCall"]
                calls.append({"name": call["name"], "args": call.get("args", {})})
            if "functionResponse" in part:
                returned = part["functionResponse"]
                returns.append({"name": returned["name"], "content": returned.get("response")})
            if part.get("text") and not part.get("thought") and content.get("role") == "model":
                answers.append(part["text"])
        if event.get("usageMetadata"):
            usage.append(event["usageMetadata"])
    return {
        "answer": "\n".join(answers),
        "tool_calls": calls,
        "tool_returns": returns,
        "model_response_events": sum(event.get("content", {}).get("role") == "model" for event in events),
        "finish_reasons": [event["finishReason"] for event in events if "finishReason" in event],
        "model_versions": sorted({event["modelVersion"] for event in events if "modelVersion" in event}),
        "usage_metadata": usage,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--interval", type=float, default=20, help="実行開始間隔の最小秒数")
    args = parser.parse_args()
    if not os.getenv("GEMINI_API_KEY"):
        raise SystemExit("GEMINI_API_KEYを設定してください。")
    started = datetime.now(ZoneInfo("Asia/Tokyo"))
    output = args.output or ROOT / "lectures/03/results" / started.strftime("%Y%m%d-%H%M%S")
    output.mkdir(parents=True, exist_ok=False)
    jobs = [(framework, key) for key in QUESTIONS for framework in ("pydantic", "adk")]
    random.Random(42).shuffle(jobs)
    jobs = [("bare", "levels"), ("bare", "tag")] + jobs
    save_json(output / "run.json", {
        "started_at": started.isoformat(), "model": MODEL,
        "versions": {name: importlib.metadata.version(name) for name in
                     ("google-adk", "google-genai", "pydantic-ai-slim")},
        "instructions": INSTRUCTIONS, "questions": QUESTIONS, "order": jobs,
        "interval_seconds": args.interval, "trials_per_question_and_framework": 1,
        "generation_settings": "SDK・モデルの既定値（temperature等は明示指定していない）",
        "history": "各質問は新しい独立した実行。ADKはadk run --in_memory --jsonl。",
        "limits": "Pydantic AI: 論理リクエスト最大6回。ADK CLI: 1問60秒。実験側の自動再試行なし。SDK内部の再試行は既定値。",
    })
    previous_start = None
    failed = 0
    for framework, key in jobs:
        if previous_start is not None:
            time.sleep(max(0, args.interval - (time.monotonic() - previous_start)))
        previous_start = time.monotonic()
        record = {"framework": framework, "question_id": key, "question": QUESTIONS[key],
                  "started_at": datetime.now(ZoneInfo("Asia/Tokyo")).isoformat()}
        print(f"[{framework}/{key}] running", flush=True)
        try:
            if framework == "pydantic":
                record.update(run_pydantic(QUESTIONS[key], output / f"{framework}_{key}.json"))
            elif framework == "adk":
                record.update(run_adk(QUESTIONS[key], output / f"{framework}_{key}.txt"))
            else:
                record.update(answer=ask(QUESTIONS[key]), requests=1)
            if not record["answer"].strip():
                raise RuntimeError("回答テキストが返りませんでした。")
            record["status"] = "ok"
        except Exception as error:
            record.update(status="error", error_type=type(error).__name__)
            failed += 1
            # API例外にはURL等が含まれる場合があるため、メッセージは共有ログに保存しない。
        with (output / "results.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(f"[{framework}/{key}] {record['status']}", flush=True)
    print(f"Results: {output}", flush=True)
    if failed:
        raise SystemExit(f"{failed}件の実行に失敗しました。保存した結果を確認してください。")


if __name__ == "__main__":
    main()
