"""The benchmark command: the run loop, the cost limit, the access check, and the command itself.

Nothing here uses the internet or a real key. Where the whole command is run,
the real Anthropic client is used with only the network replaced.
"""

import json
from datetime import datetime
from types import SimpleNamespace

import anthropic
import httpx2
import pytest

import benchmark
from benchmark import check_access, measure, run_benchmark
from rasd.data import Expected, SampleReport
from rasd.understand import DEFAULT_MODEL, Understanding


def sample(id) -> SampleReport:
    return SampleReport(id=id, sent_at=datetime(2026, 12, 22, 8, 0), lang="ar-sa", text=f"message {id}")


def answer(input_tokens=1000, output_tokens=100) -> Understanding:
    return Understanding(
        type="water",
        loc_kind="room",
        loc_number="907",
        urgency="medium",
        owner="maintenance",
        deadline_minutes=60,
        confidence="high",
        needs_confirmation=False,
        reasons=(),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


def test_run_asks_about_every_report_and_keeps_each_answer():
    seen = []

    def understand_one(text):
        seen.append(text)
        return answer()

    run = run_benchmark([sample(1), sample(2), sample(3)], understand_one, "claude-haiku-5-5")
    assert seen == ["message 1", "message 2", "message 3"]
    assert sorted(run.results) == [1, 2, 3]
    assert run.model == "claude-haiku-5-5"
    assert run.stopped_at_cost_limit is False
    assert run.seconds >= 0


def test_run_stops_as_soon_as_the_cost_passes_the_limit():
    calls = []

    def expensive(text):
        calls.append(text)
        return answer(input_tokens=6_000_000, output_tokens=0)  # 0.60 dollars each on Haiku

    run = run_benchmark([sample(1), sample(2), sample(3), sample(4)], expensive, "claude-haiku-5-5", max_cost_usd=1.00)
    assert len(calls) == 2  # 0.60, then 1.20: over the limit, so stop
    assert run.stopped_at_cost_limit is True
    assert sorted(run.results) == [1, 2]


def test_run_refuses_a_model_with_no_known_price_before_spending_anything():
    calls = []
    with pytest.raises(ValueError, match="rasd/cost.py"):
        run_benchmark([sample(1)], lambda text: calls.append(text) or answer(), "some-new-model")
    assert calls == []


class FakeModels:
    def __init__(self, error=None):
        self.error, self.asked = error, []

    def retrieve(self, model):
        self.asked.append(model)
        if self.error:
            raise self.error


class FakeClient:
    def __init__(self, error=None):
        self.models = FakeModels(error)


def status_error(cls, status):
    request = httpx2.Request("GET", "https://api.anthropic.com/v1/models/x")
    return cls("error", response=httpx2.Response(status, request=request), body=None)


def test_access_check_passes_when_the_key_and_model_are_good():
    client = FakeClient()
    check_access(client, "claude-haiku-5-5")
    assert client.models.asked == ["claude-haiku-5-5"]


def test_access_check_names_the_key_when_it_is_rejected():
    client = FakeClient(status_error(anthropic.AuthenticationError, 401))
    with pytest.raises(RuntimeError, match="RASD_CLAUDE_KEY"):
        check_access(client, "claude-haiku-5-5")


def test_access_check_names_the_model_when_it_does_not_exist():
    client = FakeClient(status_error(anthropic.NotFoundError, 404))
    with pytest.raises(RuntimeError, match="no-such-model"):
        check_access(client, "no-such-model")


def test_access_check_reports_a_network_problem():
    request = httpx2.Request("GET", "https://api.anthropic.com/v1/models/x")
    client = FakeClient(anthropic.APIConnectionError(request=request))
    with pytest.raises(RuntimeError, match="reach"):
        check_access(client, "claude-haiku-5-5")


# --- one cost limit for the whole command ----------------------------------


def test_money_already_spent_counts_towards_the_limit():
    calls = []

    def expensive(text):
        calls.append(text)
        return answer(input_tokens=6_000_000, output_tokens=0)  # 0.60 dollars each on Haiku

    run = run_benchmark(
        [sample(1), sample(2), sample(3)], expensive, "claude-haiku-5-5", max_cost_usd=1.00, already_spent_usd=0.50
    )
    assert len(calls) == 1  # 0.50 + 0.60 is over the limit, so stop
    assert run.stopped_at_cost_limit is True


def test_nothing_is_sent_when_the_limit_was_already_passed():
    calls = []
    run = run_benchmark(
        [sample(1)], lambda text: calls.append(text) or answer(), "claude-haiku-5-5", max_cost_usd=1.00, already_spent_usd=1.20
    )
    assert calls == []
    assert run.results == {}
    assert run.stopped_at_cost_limit is True


# --- measure: the main reports, then the owner's holdout reports ------------


def expected_answer(id) -> Expected:
    return Expected(
        id=id, type="water", loc_kind="room", loc_number="907", urgency="medium", owner="maintenance",
        incident=id, needs_confirmation=False, room_in_words=False, note="",
    )  # fmt: skip


def held(id) -> SampleReport:
    return SampleReport(id=id, sent_at=datetime(2026, 12, 23, 9, 0), lang="ar-sa", text=f"held {id}")


def test_measure_reads_the_main_reports_and_then_the_holdout_reports():
    seen = []
    holdout_set = ([held(1), held(2)], {1: expected_answer(1), 2: expected_answer(2)})
    run, holdout = measure(
        "claude-haiku-5-5", lambda text: seen.append(text) or answer(), [sample(1), sample(2), sample(3)], holdout_set
    )
    assert seen == ["message 1", "message 2", "message 3", "held 1", "held 2"]
    assert sorted(run.results) == [1, 2, 3]
    assert sorted(holdout.run.results) == [1, 2]
    assert holdout.reports == holdout_set[0] and holdout.expected == holdout_set[1]


def test_measure_gives_no_holdout_when_there_are_no_holdout_reports():
    run, holdout = measure("claude-haiku-5-5", lambda text: answer(), [sample(1)], None)
    assert sorted(run.results) == [1]
    assert holdout is None


def test_measure_shares_one_cost_limit_between_the_main_and_the_holdout_reports():
    seen = []

    def expensive(text):
        seen.append(text)
        return answer(input_tokens=4_000_000, output_tokens=0)  # 0.40 dollars each on Haiku

    holdout_set = ([held(1), held(2), held(3)], {i: expected_answer(i) for i in (1, 2, 3)})
    run, holdout = measure("claude-haiku-5-5", expensive, [sample(1), sample(2)], holdout_set, max_cost_usd=1.00)
    assert seen == ["message 1", "message 2", "held 1"]  # 0.80 after the main reports, 1.20 after one more
    assert run.stopped_at_cost_limit is False
    assert holdout.run.stopped_at_cost_limit is True


def test_measure_tells_the_caller_which_set_it_is_reading():
    progress = []
    holdout_set = ([held(1)], {1: expected_answer(1)})
    measure(
        "claude-haiku-5-5", lambda text: answer(), [sample(1), sample(2)], holdout_set,
        on_progress=lambda *step: progress.append(step),
    )  # fmt: skip
    assert progress == [("main", 1, 2), ("main", 2, 2), ("holdout", 1, 1)]


# --- the whole command, offline ---------------------------------------------

GOOD_READING = {
    "type": "water",
    "location_kind": "room",
    "number_words": "",
    "location_number": "",
    "urgency": "medium",
    "confidence": "high",
}


@pytest.fixture
def offline(monkeypatch, tmp_path):
    """Lets main() run with no internet and no real key.

    Every question to the model gets the same answer, files are written in a
    temporary folder, and the real data/holdout folder is not read.
    """
    asked = []  # the model each question was sent to

    def handler(request):
        if request.method == "GET":  # the free access check
            model = request.url.path.rsplit("/", 1)[-1]
            return httpx2.Response(
                200, json={"id": model, "type": "model", "display_name": model, "created_at": "2026-01-01T00:00:00Z"}
            )
        asked.append(json.loads(request.content)["model"])
        return httpx2.Response(
            200,
            json={
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "model": asked[-1],
                "content": [{"type": "text", "text": json.dumps(GOOD_READING)}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 1000, "output_tokens": 100},
            },
        )

    client = anthropic.Anthropic(
        api_key="test-key",
        max_retries=0,
        http_client=anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(handler)),
    )
    monkeypatch.setattr(benchmark, "make_client", lambda: client)
    monkeypatch.setattr(benchmark, "load_holdout", lambda: None)
    monkeypatch.setattr(benchmark, "RESULTS_DIR", tmp_path / "results")
    monkeypatch.setattr(benchmark, "COMPARISON_DIR", tmp_path / "comparison")
    return SimpleNamespace(asked=asked, results=tmp_path / "results", comparison=tmp_path / "comparison")


def test_the_command_reads_all_35_reports_prints_the_report_and_saves_it(offline, capsys):
    benchmark.main([])
    printed = capsys.readouterr().out
    assert offline.asked == [DEFAULT_MODEL] * 35
    assert "تقرير اختبار الدقة - رصد" in printed
    assert "التكلفة التقريبية" in printed
    saved = offline.results / f"benchmark_{DEFAULT_MODEL}.txt"
    assert "البلاغات: 35 (العربية 30، الأردو 5)" in saved.read_text(encoding="utf-8-sig")
    assert not offline.comparison.exists()


def test_the_command_reads_the_owners_holdout_reports_and_reports_them_separately(offline, capsys, monkeypatch):
    holdout_set = ([held(1), held(2)], {1: expected_answer(1), 2: expected_answer(2)})
    monkeypatch.setattr(benchmark, "load_holdout", lambda: holdout_set)
    benchmark.main([])
    printed = capsys.readouterr().out
    assert len(offline.asked) == 37
    second_part = printed.split("القسم الثاني")[1]
    assert "البلاغات: 2 (العربية 2، الأردو 0)" in second_part
    assert "held 1" not in printed


def test_a_mistake_in_the_holdout_files_stops_the_command_before_it_spends_anything(offline, monkeypatch):
    def broken():
        raise ValueError("holdout/expected.csv, report 3: the type is not valid.")

    monkeypatch.setattr(benchmark, "load_holdout", broken)
    with pytest.raises(SystemExit) as stop:
        benchmark.main([])
    assert "report 3" in str(stop.value)
    assert offline.asked == []


def test_compare_runs_both_models_on_the_same_reports_and_prints_the_gap(offline, capsys):
    benchmark.main(["--compare", "claude-sonnet-5-5"])
    printed = capsys.readouterr().out
    assert offline.asked == [DEFAULT_MODEL] * 35 + ["claude-sonnet-5-5"] * 35
    assert f"النموذج: {DEFAULT_MODEL}" in printed
    assert "النموذج: claude-sonnet-5-5" in printed
    assert "المقارنة بين النموذجين" in printed
    assert "الأكبر أغلى بنحو" in printed


def test_compare_saves_a_lasting_record_of_both_runs(offline):
    benchmark.main(["--compare", "claude-sonnet-5-5"])
    folder = offline.comparison
    assert "النموذج: claude-sonnet-5-5" in (folder / "benchmark_claude-sonnet-5-5.txt").read_text(encoding="utf-8-sig")
    assert f"النموذج: {DEFAULT_MODEL}" in (folder / f"benchmark_{DEFAULT_MODEL}.txt").read_text(encoding="utf-8-sig")
    assert "المقارنة بين النموذجين" in (folder / "comparison.txt").read_text(encoding="utf-8-sig")

    record = json.loads((folder / "answers.json").read_text(encoding="utf-8"))
    assert [run["model"] for run in record["runs"]] == [DEFAULT_MODEL, "claude-sonnet-5-5"]
    assert all(len(run["answers"]) == 35 for run in record["runs"])
    assert record["runs"][1]["answers"]["1"]["type"] == "water"
    assert record["recorded_at"]


def test_compare_refuses_to_run_a_second_time(offline):
    benchmark.main(["--compare", "claude-sonnet-5-5"])
    del offline.asked[:]
    with pytest.raises(SystemExit) as stop:
        benchmark.main(["--compare", "claude-sonnet-5-5"])
    assert "once" in str(stop.value)
    assert offline.asked == []


def test_compare_refuses_a_model_with_no_known_price_before_spending_anything(offline):
    with pytest.raises(SystemExit) as stop:
        benchmark.main(["--compare", "some-new-model"])
    assert "rasd/cost.py" in str(stop.value)
    assert offline.asked == []
    assert not offline.comparison.exists()


def test_compare_needs_a_model_other_than_the_everyday_one(offline):
    with pytest.raises(SystemExit):
        benchmark.main(["--compare", DEFAULT_MODEL])
    assert offline.asked == []


def test_compare_does_not_store_the_answers_to_holdout_reports_in_the_record(offline, monkeypatch):
    holdout_set = ([held(1), held(2)], {1: expected_answer(1), 2: expected_answer(2)})
    monkeypatch.setattr(benchmark, "load_holdout", lambda: holdout_set)
    benchmark.main(["--compare", "claude-sonnet-5-5"])
    record = json.loads((offline.comparison / "answers.json").read_text(encoding="utf-8"))
    assert all(len(run["answers"]) == 35 for run in record["runs"])
    assert len(offline.asked) == 74


def test_the_command_waits_and_asks_again_when_the_api_says_slow_down(monkeypatch, tmp_path, capsys):
    """35 reports in a row can hit the rate limit of a new key. That must not count as a wrong answer."""
    posts = []

    def handler(request):
        if request.method == "GET":
            return httpx2.Response(200, json={"id": "m", "type": "model", "display_name": "m", "created_at": "2026-01-01T00:00:00Z"})
        posts.append(request)
        if len(posts) in (2, 3, 4, 5):  # the second report is told to slow down four times
            error = {"type": "error", "error": {"type": "rate_limit_error", "message": "slow down"}}
            return httpx2.Response(429, json=error, headers={"retry-after-ms": "1"})
        return httpx2.Response(
            200,
            json={
                "id": "msg_test", "type": "message", "role": "assistant", "model": DEFAULT_MODEL,
                "content": [{"type": "text", "text": json.dumps(GOOD_READING)}],
                "stop_reason": "end_turn", "stop_sequence": None,
                "usage": {"input_tokens": 1000, "output_tokens": 100},
            },
        )  # fmt: skip

    client = anthropic.Anthropic(
        api_key="test-key",
        max_retries=2,  # what the live system uses
        http_client=anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(handler)),
    )
    monkeypatch.setattr(benchmark, "make_client", lambda: client)
    monkeypatch.setattr(benchmark, "load_holdout", lambda: None)
    monkeypatch.setattr(benchmark, "RESULTS_DIR", tmp_path / "results")
    monkeypatch.setattr(benchmark, "COMPARISON_DIR", tmp_path / "comparison")

    benchmark.main([])
    assert "بلاغات لم يُجب عنها النموذج: 0" in capsys.readouterr().out
    assert len(posts) == 35 + 4
