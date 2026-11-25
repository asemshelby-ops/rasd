"""The benchmark command: the run loop, the cost limit and the access check."""

from datetime import datetime

import anthropic
import httpx2
import pytest

from benchmark import check_access, run_benchmark
from rasd.data import SampleReport
from rasd.understand import Understanding


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
