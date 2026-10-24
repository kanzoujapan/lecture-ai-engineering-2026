"""第1回の計測を、実際のSDKと偽のHTTP応答で検証する。外部APIは呼ばない。"""

import json
import sys

import httpx
import pytest

from app import ask, benchmark

TEST_KEY = "offline-test-key-not-a-real-credential"


@pytest.fixture
def offline_client(monkeypatch):
    original = ask.genai.Client
    monkeypatch.setenv("GEMINI_API_KEY", TEST_KEY)

    def make(handler):
        def factory(**kwargs):
            # 本番のタイムアウト・再試行設定を保ち、HTTP通信だけ差し替える。
            kwargs["http_options"].client_args = {"transport": httpx.MockTransport(handler)}
            return original(**kwargs)

        monkeypatch.setattr(ask.genai, "Client", factory)
        return ask.create_client()

    return make


def response_json(*, reason="STOP", usage=True):
    body = {
        "candidates": [{"content": {"role": "model", "parts": [{"text": "テスト回答"}]}, "finishReason": reason}],
        "modelVersion": "test-model-version",
    }
    if usage:
        body["usageMetadata"] = {
            "promptTokenCount": 11, "candidatesTokenCount": 17,
            "thoughtsTokenCount": 23, "totalTokenCount": 51,
            "cachedContentTokenCount": 5,
        }
    return body


def read_records(output_dir):
    return [json.loads(line) for line in (output_dir / "results.jsonl").read_text().splitlines()]


def test_measure_uses_api_token_counts_and_elapsed_time(offline_client, monkeypatch):
    requests = []

    def handle(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=response_json())

    ticks = iter([10.0, 12.5])
    monkeypatch.setattr(ask, "perf_counter", lambda: next(ticks))
    with offline_client(handle) as client:
        result = ask.measure(client, "質問", model="test-model", temperature=0.5, max_output_tokens=512)

    assert result.text == "テスト回答"
    assert result.elapsed_seconds == 2.5
    assert (result.input_tokens, result.output_tokens, result.thoughts_tokens, result.total_tokens) == (11, 17, 23, 51)
    assert result.cached_tokens == 5
    assert result.model_version == "test-model-version"
    assert result.finish_reason == "STOP"
    assert len(requests) == 1
    assert requests[0]["generationConfig"]["temperature"] == 0.5
    assert requests[0]["generationConfig"]["maxOutputTokens"] == 512


def test_missing_usage_is_not_reported_as_zero(offline_client):
    with offline_client(lambda request: httpx.Response(200, json=response_json(usage=False))) as client:
        result = ask.measure(client, "質問")
    assert result.input_tokens is None
    assert result.output_tokens is None
    assert result.total_tokens is None
    assert "入力=未取得" in ask.format_metrics(result)


def test_sdk_does_not_silently_request_continuations(offline_client):
    calls = []

    def handle(request):
        calls.append(request)
        assert len(calls) == 1, "1計測中に追加のAPIリクエストを送らない"
        body = response_json(reason="CONTINUATION")
        body['candidates'][0]['continuationToken'] = 'b2ZmbGluZQ=='
        return httpx.Response(200, json=body)

    with offline_client(handle) as client:
        result = ask.measure(client, "質問")
    assert result.finish_reason == "CONTINUATION"
    assert len(calls) == 1


def test_all_combinations_are_saved_and_summarized(offline_client, tmp_path):
    output = tmp_path / "run"
    with offline_client(lambda request: httpx.Response(200, json=response_json())) as client:
        benchmark.run_benchmark(client, ["model-a", "model-b"], output, interval_seconds=0)
    records = read_records(output)
    assert len(records) == 18
    assert {(r['model'], r['question_id'], r['repeat']) for r in records} == {
        (model, qid, repeat) for model in ("model-a", "model-b") for qid in benchmark.QUESTIONS for repeat in (1, 2, 3)
    }
    assert all(r['status'] == 'ok' and r['text'] == 'テスト回答' for r in records)
    summary = (output / "summary.md").read_text()
    assert "試行済み: 18 / 18" in summary
    assert summary.count("| 3/3 |") == 6
    assert "11.0 (3/3) | 17.0 (3/3) | 23.0 (3/3) | 51.0 (3/3)" in summary
    settings = json.loads((output / "run.json").read_text())
    assert settings['questions'] == benchmark.QUESTIONS
    assert settings['retry_attempts'] == 1
    assert all(TEST_KEY not in file.read_text() for file in output.iterdir())


@pytest.mark.parametrize("code", [429, 503])
def test_error_stops_without_retry_and_preserves_partial_results(offline_client, tmp_path, capsys, code):
    calls = []

    def handle(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(200, json=response_json())
        return httpx.Response(code, json={"error": {"code": code, "message": TEST_KEY}})

    output = tmp_path / "partial"
    with offline_client(handle) as client:
        benchmark.run_benchmark(client, ["model-a", "model-b"], output, interval_seconds=0)
    records = read_records(output)
    assert len(calls) == 2  # SDK自身による再試行もない。
    assert [r['status'] for r in records] == ['ok', 'api_error']
    assert records[1]['error_code'] == code
    assert 'input_tokens' not in records[1]
    assert "試行済み: 2 / 18" in (output / "summary.md").read_text()
    assert TEST_KEY not in capsys.readouterr().out
    assert all(TEST_KEY not in file.read_text() for file in output.iterdir())


def test_truncated_answers_are_retained_but_not_averaged(offline_client, tmp_path):
    output = tmp_path / "incomplete"
    with offline_client(lambda request: httpx.Response(200, json=response_json(reason="MAX_TOKENS"))) as client:
        benchmark.run_benchmark(client, ["model-a"], output, repeats=1, interval_seconds=0)
    records = read_records(output)
    assert len(records) == 3
    assert all(r['status'] == 'incomplete' and r['text'] == 'テスト回答' for r in records)
    summary = (output / "summary.md").read_text()
    assert "完了: 0 回" in summary
    assert "11.0" not in summary


def test_timeout_is_saved_without_secret_details(offline_client, tmp_path, capsys):
    calls = []

    def handle(request):
        calls.append(request)
        raise httpx.ReadTimeout(TEST_KEY, request=request)

    output = tmp_path / "timeout"
    with offline_client(handle) as client:
        benchmark.run_benchmark(client, ["model-a"], output, interval_seconds=0)
    assert len(calls) == 1
    assert read_records(output)[0]['status'] == 'network_error'
    assert TEST_KEY not in capsys.readouterr().out
    assert TEST_KEY not in (output / "results.jsonl").read_text()


def test_pacing_is_excluded_from_latency(offline_client, tmp_path, monkeypatch):
    clock = [0.0]
    sleeps = []

    def handle(request):
        clock[0] += 2.0
        return httpx.Response(200, json=response_json())

    def sleep(seconds):
        sleeps.append(seconds)
        clock[0] += seconds

    monkeypatch.setattr(ask, "perf_counter", lambda: clock[0])
    monkeypatch.setattr(benchmark.time, "perf_counter", lambda: clock[0])
    monkeypatch.setattr(benchmark.time, "sleep", sleep)
    with offline_client(handle) as client:
        records = benchmark.run_benchmark(client, ["model-a"], tmp_path / "paced", repeats=1)
    assert sleeps == [13.0, 13.0]
    assert all(r['elapsed_seconds'] == 2.0 for r in records)


def test_interrupt_during_wait_keeps_received_results(offline_client, tmp_path, monkeypatch):
    def interrupt(seconds):
        raise KeyboardInterrupt

    monkeypatch.setattr(benchmark.time, "sleep", interrupt)
    output = tmp_path / "interrupted"
    with offline_client(lambda request: httpx.Response(200, json=response_json())) as client:
        benchmark.run_benchmark(client, ["model-a"], output)
    assert len(read_records(output)) == 1
    assert "試行済み: 1 / 9" in (output / "summary.md").read_text()


def test_dry_run_needs_no_key_and_makes_no_client(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(benchmark, "create_client", lambda: pytest.fail("dry-runでAPIクライアントを作らない"))
    output = tmp_path / "dry"
    monkeypatch.setattr(sys, "argv", ["benchmark", "--dry-run", "--output-dir", str(output)])
    benchmark.main()
    assert "最大18リクエスト" in capsys.readouterr().out
    assert not output.exists()
