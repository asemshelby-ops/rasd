"""Scoring one answer against the expected table, and the printed Arabic report.

All reports here are made up for the tests.
"""

from datetime import datetime

import pytest

from rasd.cost import cost_usd
from rasd.data import Expected, SampleReport, load_expected, load_reports
from rasd.scoring import Run, render, score
from rasd.understand import Understanding, understand


def expected(id=1, **changes) -> Expected:
    fields = dict(
        id=id,
        type="water",
        loc_kind="room",
        loc_number="907",
        urgency="medium",
        owner="maintenance",
        incident=id,
        needs_confirmation=False,
        room_in_words=False,
        note="",
    )
    fields.update(changes)
    return Expected(**fields)


def answer(**changes) -> Understanding:
    fields = dict(
        type="water",
        loc_kind="room",
        loc_number="907",
        urgency="medium",
        owner="maintenance",
        deadline_minutes=60,
        confidence="high",
        needs_confirmation=False,
        reasons=(),
        input_tokens=1000,
        output_tokens=100,
    )
    fields.update(changes)
    return Understanding(**fields)


def sample(id=1, lang="ar-sa", text="ما في موية في الغرفة") -> SampleReport:
    return SampleReport(id=id, sent_at=datetime(2026, 12, 22, 8, 0), lang=lang, text=text)


# --- score ----------------------------------------------------------------


def test_a_fully_correct_answer_scores_true_on_every_field():
    assert score(expected(), answer()) == {
        "type": True,
        "loc_kind": True,
        "loc_number": True,
        "urgency": True,
        "owner": True,
        "needs_confirmation": True,
    }


def test_each_wrong_field_scores_false_on_its_own():
    result = score(expected(), answer(loc_number="970", urgency="urgent"))
    assert result["loc_number"] is False
    assert result["urgency"] is False
    assert result["type"] is True


def test_an_empty_expected_cell_is_not_scored():
    result = score(
        expected(loc_kind=None, loc_number=None, urgency=None, needs_confirmation=None),
        answer(loc_kind="floor", loc_number="6", urgency="low", needs_confirmation=True),
    )
    assert result["loc_kind"] is None
    assert result["loc_number"] is None
    assert result["urgency"] is None
    assert result["needs_confirmation"] is None


def test_a_dash_means_no_number_is_expected():
    no_number = expected(loc_kind="none", loc_number="-")
    assert score(no_number, answer(loc_kind="none", loc_number=None))["loc_number"] is True
    assert score(no_number, answer(loc_kind="none", loc_number="5"))["loc_number"] is False


# --- render ---------------------------------------------------------------


def run_of(results, **changes) -> Run:
    fields = dict(model="claude-haiku-5-5", results=results, seconds=4.0, stopped_at_cost_limit=False)
    fields.update(changes)
    return Run(**fields)


def test_report_shows_accuracy_per_field_for_all_arabic_and_urdu():
    reports = [sample(1), sample(2), sample(3, lang="ur")]
    table = {1: expected(1), 2: expected(2), 3: expected(3)}
    results = {1: answer(), 2: answer(urgency="urgent"), 3: answer()}
    text = render(run_of(results), reports, table)
    assert "النوع: الكل 3 من 3 (100%) | العربية 2 من 2 (100%) | الأردو 1 من 1 (100%)" in text
    assert "الأولوية: الكل 2 من 3 (67%) | العربية 1 من 2 (50%) | الأردو 1 من 1 (100%)" in text


def test_fields_that_are_not_scored_are_left_out_of_the_count():
    reports = [sample(1), sample(2)]
    table = {1: expected(1), 2: expected(2, urgency=None)}
    text = render(run_of({1: answer(), 2: answer(urgency="low")}), reports, table)
    assert "الأولوية: الكل 1 من 1 (100%)" in text


def test_report_lists_each_wrong_report_with_expected_and_actual():
    reports = [sample(1), sample(2, text="المكيف خربان في الغرفة")]
    table = {1: expected(1), 2: expected(2, type="ac")}
    text = render(run_of({1: answer(), 2: answer(loc_number="970")}), reports, table)
    assert "البلاغات الخاطئة: 1" in text
    assert "البلاغ 2" in text and "المكيف خربان في الغرفة" in text
    assert "النوع: المتوقع «عطل تكييف»، الناتج «انقطاع الماء»" in text
    assert "رقم المكان: المتوقع «907»، الناتج «970»" in text
    assert "البلاغ 1" not in text


def test_report_says_so_when_nothing_is_wrong():
    text = render(run_of({1: answer()}), [sample(1)], {1: expected(1)})
    assert "البلاغات الخاطئة: 0" in text


def test_a_wrong_flag_shows_why_the_report_was_flagged():
    flagged = answer(needs_confirmation=True, reasons=("number_not_confirmed",))
    text = render(run_of({1: flagged}), [sample(1)], {1: expected(1)})
    assert "الإحالة لتأكيد المشرف: المتوقع «لا»، الناتج «نعم»" in text
    assert "رقم المكان لم يتأكد آلياً" in text


def test_spoken_room_numbers_are_reported_separately():
    reports = [sample(1), sample(2), sample(3), sample(4)]
    table = {
        1: expected(1, room_in_words=True),
        2: expected(2, room_in_words=True),
        3: expected(3, room_in_words=True),
        4: expected(4, room_in_words=False),
    }
    results = {
        1: answer(),
        2: answer(loc_number="970", needs_confirmation=True, reasons=("number_not_confirmed",)),
        3: answer(loc_number="709"),
        4: answer(loc_number="111"),
    }
    text = render(run_of(results), reports, table)
    assert "رقم الغرفة صحيح: 1 من 3 (33%)" in text
    assert "رقم خاطئ ونُبّه المشرف عليه: 1" in text
    assert "رقم خاطئ ولم يُنبَّه عليه: 1" in text


def test_report_shows_model_cost_and_time():
    results = {1: answer(input_tokens=1000, output_tokens=100), 2: answer(input_tokens=3000, output_tokens=300)}
    text = render(run_of(results, seconds=4.0), [sample(1), sample(2)], {1: expected(1), 2: expected(2)})
    assert "النموذج: claude-haiku-5-5" in text
    assert "4000" in text and "400" in text
    assert f"{cost_usd('claude-haiku-5-5', 4000, 400):.4f} دولار" in text
    assert "4.0 ثانية" in text and "2.0 ثانية للبلاغ" in text


def test_report_says_duplicate_grouping_is_not_built_yet():
    text = render(run_of({1: answer()}), [sample(1)], {1: expected(1)})
    assert "تجميع البلاغات المكررة" in text and "لم يُبنَ بعد" in text


def test_report_counts_the_reports_the_model_did_not_answer():
    failed = answer(type="unclear", needs_confirmation=True, reasons=("not_understood",), error="could not reach the API")
    text = render(run_of({1: answer(), 2: failed}), [sample(1), sample(2)], {1: expected(1), 2: expected(2)})
    assert "بلاغات لم يُجب عنها النموذج: 1" in text
    assert "could not reach the API" in text


def test_report_warns_when_the_run_stopped_at_the_cost_limit():
    reports = [sample(1), sample(2)]
    table = {1: expected(1), 2: expected(2)}
    text = render(run_of({1: answer()}, stopped_at_cost_limit=True), reports, table)
    assert "توقف الاختبار" in text
    assert "1 من 2" in text


def test_every_line_of_the_report_starts_right_to_left():
    text = render(run_of({1: answer()}), [sample(1)], {1: expected(1)})
    assert all(line.startswith("‏") for line in text.splitlines() if line)


def test_the_report_can_be_built_for_the_real_reports_even_when_nothing_was_understood():
    reports, table = load_reports(), load_expected()
    results = {r.id: understand("", client=None) for r in reports}  # an empty message never reaches the model
    text = render(run_of(results), reports, table)
    assert "البلاغات: 35 (العربية 30، الأردو 5)" in text
    assert "بلاغات لم يُجب عنها النموذج: 35" in text
    assert "رقم الغرفة صحيح: 0 من 13 (0%)" in text


# --- cost -----------------------------------------------------------------


def test_cost_uses_the_price_of_each_model():
    assert cost_usd("claude-haiku-5-5", 1_000_000, 1_000_000) == pytest.approx(0.60)
    assert cost_usd("claude-sonnet-5-5", 1_000_000, 1_000_000) == pytest.approx(12.00)


def test_cost_of_an_unknown_model_is_an_error_not_a_guess():
    with pytest.raises(ValueError, match="rasd/cost.py"):
        cost_usd("some-new-model", 1000, 1000)
