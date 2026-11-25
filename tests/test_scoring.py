"""Scoring one answer against the expected table, and the printed Arabic report.

All reports here are made up for the tests.
"""

from datetime import datetime, timedelta

import pytest

from rasd.cost import cost_usd
from rasd.data import Expected, SampleReport, load_expected, load_reports
from rasd.incidents import MERGE_WINDOW_MINUTES
from rasd.scoring import Holdout, Run, render, render_comparison, render_holdout, render_stability, score
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


def sample(id=1, lang="ar-sa", text="ما في موية في الغرفة", minutes=0) -> SampleReport:
    sent_at = datetime(2026, 12, 22, 8, 0) + timedelta(minutes=minutes)
    return SampleReport(id=id, sent_at=sent_at, lang=lang, text=text)


# --- score ----------------------------------------------------------------


def test_a_fully_correct_answer_scores_true_on_every_field():
    assert score(expected(), answer()) == {
        "type": True,
        "hotel": None,  # the expected answers of this report give no hotel, name or question to score
        "loc_kind": True,
        "loc_number": True,
        "name": None,
        "urgency": True,
        "owner": True,
        "needs_confirmation": True,
        "ask": None,
    }


def test_each_wrong_field_scores_false_on_its_own():
    result = score(expected(), answer(loc_number="970", urgency="urgent"))
    assert result["loc_number"] is False
    assert result["urgency"] is False
    assert result["type"] is True


def test_an_empty_expected_cell_is_not_scored():
    result = score(
        expected(loc_kind=None, loc_number=None, urgency=None, needs_confirmation=None),
        answer(loc_kind="floor", loc_number="6", urgency="normal", needs_confirmation=True),
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
    text = render(run_of({1: answer(), 2: answer(urgency="normal")}), reports, table)
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
    assert "البلاغات: 58 (العربية 50، الأردو 8)" in text
    assert "بلاغات لم يُجب عنها النموذج: 58" in text
    assert "رقم الغرفة صحيح: 0 من 15 (0%)" in text


# --- cost -----------------------------------------------------------------


def test_cost_uses_the_price_of_each_model():
    assert cost_usd("claude-haiku-5-5", 1_000_000, 1_000_000) == pytest.approx(0.60)
    assert cost_usd("claude-sonnet-5-5", 1_000_000, 1_000_000) == pytest.approx(12.00)


def test_cost_of_an_unknown_model_is_an_error_not_a_guess():
    with pytest.raises(ValueError, match="rasd/cost.py"):
        cost_usd("some-new-model", 1000, 1000)


# --- confident mistakes: wrong, and nobody was asked to check --------------


def confident_section(text: str) -> str:
    return text.split("== الأخطاء الواثقة")[1].split("\n\n")[0]


def test_a_wrong_room_that_was_not_flagged_is_a_confident_mistake():
    reports = [sample(1), sample(2, minutes=5)]
    table = {1: expected(1), 2: expected(2, loc_number="355")}
    text = render(run_of({1: answer(), 2: answer(loc_number="335")}), reports, table)
    section = confident_section(text)
    assert "بلاغات فيها خطأ ولم تُحَل للمشرف: 1 من 2" in section
    assert "أرقامها: 2" in section
    assert "منها بمكان خاطئ (الفندق أو نوعه أو رقمه): 1" in section
    assert "بلاغات فيها خطأ وأُحيلت للمشرف: 0" in section


def test_a_wrong_room_that_was_flagged_is_not_a_confident_mistake():
    flagged = answer(loc_number="335", needs_confirmation=True, reasons=("number_not_confirmed",))
    text = render(run_of({1: flagged}), [sample(1)], {1: expected(1, loc_number="355")})
    section = confident_section(text)
    assert "بلاغات فيها خطأ ولم تُحَل للمشرف: 0 من 1" in section
    assert "أرقامها" not in section
    assert "منها بمكان خاطئ (الفندق أو نوعه أو رقمه): 0" in section
    assert "بلاغات فيها خطأ وأُحيلت للمشرف: 1" in section


def test_a_wrong_kind_of_place_counts_as_a_wrong_place():
    text = render(run_of({1: answer(loc_kind="floor")}), [sample(1)], {1: expected(1)})
    assert "منها بمكان خاطئ (الفندق أو نوعه أو رقمه): 1" in confident_section(text)


def test_a_wrong_urgency_that_was_not_flagged_is_a_confident_mistake_but_not_a_wrong_place():
    text = render(run_of({1: answer(urgency="normal")}), [sample(1)], {1: expected(1)})
    section = confident_section(text)
    assert "بلاغات فيها خطأ ولم تُحَل للمشرف: 1 من 1" in section
    assert "منها بمكان خاطئ (الفندق أو نوعه أو رقمه): 0" in section


def test_a_report_that_should_have_gone_to_the_supervisor_but_did_not_is_a_confident_mistake():
    text = render(run_of({1: answer()}), [sample(1)], {1: expected(1, needs_confirmation=True)})
    assert "بلاغات فيها خطأ ولم تُحَل للمشرف: 1 من 1" in confident_section(text)


def test_a_correct_report_that_was_flagged_anyway_is_a_needless_referral_not_a_mistake():
    flagged = answer(needs_confirmation=True, reasons=("number_not_confirmed",))
    text = render(run_of({1: flagged}), [sample(1)], {1: expected(1)})
    section = confident_section(text)
    assert "بلاغات فيها خطأ ولم تُحَل للمشرف: 0 من 1" in section
    assert "بلاغات فيها خطأ وأُحيلت للمشرف: 0" in section
    assert "إحالات للمشرف بلا داعٍ (البلاغ مفهوم صحيحاً): 1" in section


def test_fields_that_are_not_scored_cannot_make_a_confident_mistake():
    table = {1: expected(1, loc_kind=None, loc_number=None, urgency=None, needs_confirmation=None)}
    text = render(run_of({1: answer(loc_number="111", urgency="normal")}), [sample(1)], table)
    assert "بلاغات فيها خطأ ولم تُحَل للمشرف: 0 من 1" in confident_section(text)


def test_each_wrong_report_is_labelled_with_what_happened_to_it():
    reports = [sample(1), sample(2, minutes=5), sample(3, minutes=9)]
    table = {1: expected(1), 2: expected(2, loc_number="355"), 3: expected(3, loc_number="601")}
    results = {
        1: answer(urgency="normal"),
        2: answer(loc_number="335", needs_confirmation=True, reasons=("number_not_confirmed",)),
        3: answer(loc_number="601", needs_confirmation=True, reasons=("low_confidence",)),
    }
    text = render(run_of(results), reports, table)
    assert "البلاغ 1 (العربية، خطأ واثق):" in text
    assert "البلاغ 2 (العربية، أُحيل للمشرف):" in text
    assert "البلاغ 3 (العربية، إحالة بلا داعٍ):" in text


# --- duplicate grouping ----------------------------------------------------


def grouping_section(text: str) -> str:
    return text.split("== تجميع البلاغات المكررة ==")[1].split("\n\n")[0]


def three_reports_two_incidents():
    """Reports 1 and 2 are the same incident; report 3 is another room."""
    reports = [sample(1), sample(2, minutes=5), sample(3, minutes=9)]
    table = {1: expected(1, incident=1), 2: expected(2, incident=1), 3: expected(3, incident=2, loc_number="355")}
    return reports, table


def test_grouping_score_when_duplicates_are_merged_correctly():
    reports, table = three_reports_two_incidents()
    results = {1: answer(), 2: answer(), 3: answer(loc_number="355")}
    section = grouping_section(render(run_of(results), reports, table))
    assert f"نافذة الدمج: {MERGE_WINDOW_MINUTES} دقيقة" in section
    assert "عدد الحوادث: المتوقع 2، الناتج 2" in section
    assert "بلاغات في حادثتها الصحيحة: 3 من 3 (100%)" in section
    assert "حوادث مكررة جُمعت كاملة: 1 من 1" in section
    assert "حوادث تفرّقت بلاغاتها (تكرار لم يُدمج): 0" in section
    assert "حوادث دُمجت فيها بلاغات مختلفة خطأً: 0" in section


def test_a_duplicate_that_was_not_merged_is_counted_and_listed():
    reports, table = three_reports_two_incidents()
    unsure = answer(needs_confirmation=True, reasons=("number_not_confirmed",))
    results = {1: answer(), 2: unsure, 3: answer(loc_number="355")}
    section = grouping_section(render(run_of(results), reports, table))
    assert "عدد الحوادث: المتوقع 2، الناتج 3" in section
    assert "بلاغات في حادثتها الصحيحة: 1 من 3 (33%)" in section
    assert "حوادث مكررة جُمعت كاملة: 0 من 1" in section
    assert "حوادث تفرّقت بلاغاتها (تكرار لم يُدمج): 1" in section
    assert "  - المتوقع معاً: 1، 2. الناتج: 1 | 2" in section


def test_two_incidents_merged_by_mistake_are_counted_and_listed():
    reports, table = three_reports_two_incidents()
    results = {1: answer(), 2: answer(), 3: answer()}  # report 3 read as the same room
    section = grouping_section(render(run_of(results), reports, table))
    assert "عدد الحوادث: المتوقع 2، الناتج 1" in section
    assert "بلاغات في حادثتها الصحيحة: 0 من 3 (0%)" in section
    assert "حوادث دُمجت فيها بلاغات مختلفة خطأً: 1" in section
    assert "  - دُمجت خطأً: 1، 2، 3" in section


def test_grouping_uses_the_time_each_report_was_sent():
    reports = [sample(1), sample(2, minutes=MERGE_WINDOW_MINUTES + 30)]
    table = {1: expected(1, incident=1), 2: expected(2, incident=2)}
    section = grouping_section(render(run_of({1: answer(), 2: answer()}), reports, table))
    assert "بلاغات في حادثتها الصحيحة: 2 من 2 (100%)" in section


def test_grouping_is_not_scored_when_the_incident_column_is_not_filled_in():
    reports = [sample(1), sample(2, minutes=5)]
    table = {1: expected(1, incident=1), 2: expected(2, incident=None)}
    section = grouping_section(render(run_of({1: answer(), 2: answer()}), reports, table))
    assert "لم يُحتسب" in section and "incident" in section
    assert "بلاغات في حادثتها الصحيحة" not in section


def test_grouping_of_a_run_that_stopped_early_counts_only_the_reports_it_read():
    reports, table = three_reports_two_incidents()
    section = grouping_section(render(run_of({1: answer()}, stopped_at_cost_limit=True), reports, table))
    assert "بلاغات في حادثتها الصحيحة: 1 من 1 (100%)" in section


def test_the_real_reports_get_a_grouping_score_even_when_nothing_was_understood():
    reports, table = load_reports(), load_expected()
    results = {r.id: understand("", client=None) for r in reports}
    section = grouping_section(render(run_of(results), reports, table))
    assert "عدد الحوادث: المتوقع 46، الناتج 52" in section
    assert "حوادث مكررة جُمعت كاملة: 0 من 4" in section


# --- the owner's holdout reports -------------------------------------------

HIDDEN = "نص محجوب لا يجوز أن يظهر"


def holdout_part(text: str) -> str:
    return text.split("القسم الثاني")[1].split("== التكلفة والزمن ==")[0]


def main_part(text: str) -> str:
    return text.split("القسم الثاني")[0]


def a_holdout(results=None, **changes) -> Holdout:
    reports = [sample(1, text=HIDDEN), sample(2, text=HIDDEN, minutes=5), sample(3, lang="ur", text=HIDDEN, minutes=9)]
    table = {1: expected(1), 2: expected(2, type="ac"), 3: expected(3, loc_number="355")}
    results = results or {1: answer(), 2: answer(), 3: answer(loc_number="355")}
    return Holdout(run=run_of(results, **changes), reports=reports, expected=table)


def test_report_says_where_holdout_reports_go_when_there_are_none():
    text = render(run_of({1: answer()}), [sample(1)], {1: expected(1)})
    assert "القسم الأول: البلاغات الأساسية" in text
    assert "القسم الثاني: البلاغات المحجوبة" in text
    assert "لا توجد بلاغات محجوبة بعد" in holdout_part(text)
    assert "data/holdout" in holdout_part(text)


def test_holdout_results_are_reported_separately_from_the_main_reports():
    reports = [sample(1), sample(2, minutes=5)]
    table = {1: expected(1), 2: expected(2, loc_number="601")}
    main_results = {1: answer(), 2: answer(loc_number="601")}
    text = render(run_of(main_results), reports, table, holdout=a_holdout())
    assert "البلاغات: 2 (العربية 2، الأردو 0)" in main_part(text)
    assert "النوع: الكل 2 من 2 (100%)" in main_part(text)
    assert "البلاغات: 3 (العربية 2، الأردو 1)" in holdout_part(text)
    assert "النوع: الكل 2 من 3 (67%) | العربية 1 من 2 (50%) | الأردو 1 من 1 (100%)" in holdout_part(text)
    assert "بلاغات فيها خطأ ولم تُحَل للمشرف: 1 من 3" in holdout_part(text)
    assert "بلاغات فيها خطأ ولم تُحَل للمشرف: 0 من 2" in main_part(text)


def test_holdout_section_has_its_own_grouping_score():
    text = render(run_of({1: answer()}), [sample(1)], {1: expected(1)}, holdout=a_holdout())
    # Report 2 was read as the same problem in the same room as report 1, so they were merged.
    assert "عدد الحوادث: المتوقع 3، الناتج 2" in holdout_part(text)


def test_holdout_wrong_reports_are_listed_by_number_without_their_text():
    wrong = {
        1: answer(),
        2: answer(),
        3: answer(loc_number="335", number_words="كلمات محجوبة"),
    }
    text = render(run_of({1: answer()}), [sample(1)], {1: expected(1)}, holdout=a_holdout(wrong))
    part = holdout_part(text)
    assert "البلاغ 2 (العربية، خطأ واثق)" in part
    assert "النوع: المتوقع «عطل تكييف»، الناتج «انقطاع الماء»" in part
    assert "البلاغ 3 (الأردو، خطأ واثق)" in part
    assert "رقم المكان: المتوقع «355»، الناتج «335»" in part
    assert HIDDEN not in text
    assert "كلمات محجوبة" not in text
    assert "لا تُطبع" in part  # the section says why the texts are missing


def test_cost_and_time_cover_the_main_and_the_holdout_reports_together():
    main = run_of({1: answer(input_tokens=1000, output_tokens=100)}, seconds=2.0)
    holdout = a_holdout(seconds=6.0)  # 3 answers of 1000 and 100 tokens
    text = render(main, [sample(1)], {1: expected(1)}, holdout=holdout)
    assert "4000 داخلة و400 خارجة" in text
    assert f"{cost_usd('claude-haiku-5-5', 4000, 400):.4f} دولار" in text
    assert "8.0 ثانية" in text and "2.0 ثانية للبلاغ" in text


def test_a_holdout_report_the_model_did_not_answer_is_listed_as_a_holdout_report():
    failed = answer(type="unclear", needs_confirmation=True, reasons=("not_understood",), error="could not reach the API")
    holdout = a_holdout({1: answer(), 2: failed, 3: answer(loc_number="355")})
    text = render(run_of({1: answer()}), [sample(1)], {1: expected(1)}, holdout=holdout)
    assert "بلاغات لم يُجب عنها النموذج: 1" in text
    assert "رقم 2 (من المحجوبة): could not reach the API" in text


def test_report_warns_when_the_holdout_part_stopped_at_the_cost_limit():
    holdout = a_holdout({1: answer()}, stopped_at_cost_limit=True)
    text = render(run_of({1: answer()}), [sample(1)], {1: expected(1)}, holdout=holdout)
    assert "توقف الاختبار" in holdout_part(text)
    assert "توقف الاختبار" not in main_part(text)


def test_every_line_is_right_to_left_with_a_holdout_too():
    text = render(run_of({1: answer()}), [sample(1)], {1: expected(1)}, holdout=a_holdout())
    assert all(line.startswith("‏") for line in text.splitlines() if line)


# --- the comparison of two models ------------------------------------------


def two_runs():
    """Three reports. The smaller model gets one room wrong (flagged); the larger gets all right."""
    reports = [sample(1), sample(2, minutes=5), sample(3, lang="ur", minutes=9)]
    table = {
        1: expected(1, incident=1, room_in_words=True),
        2: expected(2, incident=1, room_in_words=True),
        3: expected(3, incident=2, loc_number="355"),
    }
    small = run_of(
        {
            1: answer(),
            2: answer(loc_number="970", needs_confirmation=True, reasons=("number_not_confirmed",)),
            3: answer(loc_number="355"),
        },
        seconds=3.0,
    )
    large = run_of(
        {
            1: answer(input_tokens=1000, output_tokens=300),
            2: answer(input_tokens=1000, output_tokens=300),
            3: answer(loc_number="355", input_tokens=1000, output_tokens=300),
        },
        model="claude-sonnet-5-5",
        seconds=9.0,
    )
    return small, large, reports, table


def test_comparison_names_both_models():
    text = render_comparison(*two_runs())
    assert "الأصغر: claude-haiku-5-5" in text
    assert "الأكبر: claude-sonnet-5-5" in text


def test_comparison_shows_each_field_for_both_models_and_who_is_better():
    text = render_comparison(*two_runs())
    assert "النوع: الأصغر 3 من 3 (100%) | الأكبر 3 من 3 (100%) | لا فرق" in text
    assert "رقم المكان: الأصغر 2 من 3 (67%) | الأكبر 3 من 3 (100%) | الأكبر أفضل بـ 1" in text
    assert "كل الحقول معاً: الأصغر 2 من 3 (67%) | الأكبر 3 من 3 (100%) | الأكبر أفضل بـ 1" in text


def test_comparison_says_so_when_the_smaller_model_is_better():
    small, large, reports, table = two_runs()
    text = render_comparison(large, small, reports, table)  # swapped on purpose
    assert "رقم المكان: الأصغر 3 من 3 (100%) | الأكبر 2 من 3 (67%) | الأصغر أفضل بـ 1" in text


def test_comparison_splits_all_fields_by_language():
    text = render_comparison(*two_runs())
    assert "كل الحقول معاً (العربية): الأصغر 1 من 2 (50%) | الأكبر 2 من 2 (100%) | الأكبر أفضل بـ 1" in text
    assert "كل الحقول معاً (الأردو): الأصغر 1 من 1 (100%) | الأكبر 1 من 1 (100%) | لا فرق" in text


def test_comparison_shows_spoken_rooms_and_grouping():
    text = render_comparison(*two_runs())
    assert "رقم الغرفة المنطوق بالكلمات: الأصغر 1 من 2 (50%) | الأكبر 2 من 2 (100%) | الأكبر أفضل بـ 1" in text
    assert "بلاغات في حادثتها الصحيحة: الأصغر 1 من 3 (33%) | الأكبر 3 من 3 (100%) | الأكبر أفضل بـ 2" in text


def test_comparison_shows_confident_mistakes_for_both_models():
    small, large, reports, table = two_runs()
    large.results[3] = answer(loc_number="335", input_tokens=1000, output_tokens=300)  # wrong and not flagged
    text = render_comparison(small, large, reports, table)
    assert "بلاغات فيها خطأ ولم تُحَل للمشرف: الأصغر 0 | الأكبر 1" in text
    assert "منها بمكان خاطئ (الفندق أو نوعه أو رقمه): الأصغر 0 | الأكبر 1" in text


def test_comparison_shows_the_cost_gap():
    small, large, reports, table = two_runs()
    text = render_comparison(small, large, reports, table)
    small_cost = cost_usd("claude-haiku-5-5", 3000, 300)
    large_cost = cost_usd("claude-sonnet-5-5", 3000, 900)
    assert f"التكلفة التقريبية: الأصغر {small_cost:.4f} دولار | الأكبر {large_cost:.4f} دولار" in text
    assert f"الأكبر أغلى بنحو {round(large_cost / small_cost)} مرة" in text


def test_comparison_shows_the_time_per_report():
    text = render_comparison(*two_runs())
    assert "الزمن للبلاغ: الأصغر 1.0 ثانية | الأكبر 3.0 ثانية" in text


def test_comparison_warns_when_a_run_stopped_at_the_cost_limit():
    small, large, reports, table = two_runs()
    large.stopped_at_cost_limit = True
    del large.results[3]
    text = render_comparison(small, large, reports, table)
    assert "تنبيه" in text and "لم يُكمل" in text


def test_every_line_of_the_comparison_starts_right_to_left():
    text = render_comparison(*two_runs())
    assert all(line.startswith("‏") for line in text.splitlines() if line)


# --- priority: what the report shows when it is wrong ------------------------


def test_report_names_the_stage_the_expected_priorities_are_written_for():
    text = render(run_of({1: answer()}), [sample(1)], {1: expected(1)})
    assert "مرحلة الرحلة في هذا الاختبار: أيام مكة" in text


def test_a_wrong_priority_shows_the_risks_the_model_read_and_its_words():
    read = answer(urgency="urgent", risks=("elderly", "medication"), risk_words=("ختيارة", "علاجها"))
    text = render(run_of({1: read}), [sample(1)], {1: expected(1)})
    assert "الأولوية: المتوقع «متوسط»، الناتج «عاجل»" in text
    assert "(المخاطر التي قرأها النموذج: حاج كبير في السن «ختيارة»، دواء «علاجها»)" in text


def test_a_wrong_priority_says_so_when_the_model_read_no_risk():
    text = render(run_of({1: answer(urgency="normal")}), [sample(1)], {1: expected(1)})
    assert "الأولوية: المتوقع «متوسط»، الناتج «عادي» (لم يقرأ النموذج أي خطر)" in text


def test_a_wrong_priority_in_a_holdout_report_shows_the_risks_without_their_words():
    wrong = {
        1: answer(urgency="urgent", risks=("elderly",), risk_words=("كلمات محجوبة",)),
        2: answer(type="ac"),
        3: answer(loc_number="355"),
    }
    text = render(run_of({1: answer()}), [sample(1)], {1: expected(1)}, holdout=a_holdout(wrong))
    assert "(المخاطر التي قرأها النموذج: حاج كبير في السن)" in holdout_part(text)
    assert "كلمات محجوبة" not in text


def test_the_new_level_names_are_printed_in_arabic():
    text = render(run_of({1: answer(urgency="critical")}), [sample(1)], {1: expected(1, urgency="normal")})
    assert "الأولوية: المتوقع «عادي»، الناتج «حرج»" in text


# --- a report for the holdout reports alone ---------------------------------


def test_the_holdout_only_report_has_the_holdout_section_and_no_main_section():
    text = render_holdout(a_holdout())
    assert "القسم الثاني: البلاغات المحجوبة" not in text  # there is no first section here
    assert "البلاغات المحجوبة (كتبها مالك المشروع وفريقه)" in text
    assert "البلاغات الأساسية" not in text
    assert "البلاغات: 3 (العربية 2، الأردو 1)" in text
    assert "النوع: الكل 2 من 3 (67%)" in text


def test_the_holdout_only_report_never_prints_the_text_of_a_report():
    wrong = {1: answer(), 2: answer(), 3: answer(loc_number="335", number_words="كلمات محجوبة")}
    text = render_holdout(a_holdout(wrong))
    assert "البلاغ 3 (الأردو، خطأ واثق)" in text
    assert HIDDEN not in text and "كلمات محجوبة" not in text
    assert "لا تُطبع" in text


def test_the_holdout_only_report_shows_model_stage_cost_and_time():
    text = render_holdout(a_holdout(seconds=6.0))
    assert "النموذج: claude-haiku-5-5" in text
    assert "مرحلة الرحلة في هذا الاختبار: أيام مكة" in text
    assert "3000 داخلة و300 خارجة" in text
    assert f"{cost_usd('claude-haiku-5-5', 3000, 300):.4f} دولار" in text
    assert "6.0 ثانية (2.0 ثانية للبلاغ في المتوسط)" in text


def test_every_line_of_the_holdout_only_report_starts_right_to_left():
    assert all(line.startswith("‏") for line in render_holdout(a_holdout()).splitlines() if line)


def test_the_comparison_can_be_titled_for_the_holdout_reports():
    small, large, reports, table = two_runs()
    assert "(البلاغات الأساسية)" in render_comparison(small, large, reports, table)
    text = render_comparison(small, large, reports, table, holdout=True)
    assert "(البلاغات المحجوبة)" in text and "(البلاغات الأساسية)" not in text


# --- stability: the same reports read several times --------------------------


def three_runs(second=None, third=None):
    """Three runs over three reports. The first run is all right; the others may differ."""
    reports = [sample(1), sample(2, minutes=30), sample(3, lang="ur", minutes=50)]
    table = {1: expected(1), 2: expected(2, loc_number="355"), 3: expected(3, loc_number="601")}
    right = {1: answer(), 2: answer(loc_number="355"), 3: answer(loc_number="601")}
    runs = [run_of(dict(right)), run_of({**right, **(second or {})}), run_of({**right, **(third or {})})]
    return runs, reports, table


def test_stability_says_how_many_runs_it_compares():
    text = render_stability(*three_runs())
    assert "الثبات بين التشغيلات: 3 تشغيلات (البلاغات الأساسية)" in text


def test_stability_shows_all_fields_right_and_confident_mistakes_for_each_run():
    text = render_stability(*three_runs(second={2: answer(loc_number="335")}))
    assert "كل الحقول معاً في كل تشغيل: 3 من 3، 2 من 3، 3 من 3" in text
    assert "بلاغات فيها خطأ ولم تُحَل للمشرف في كل تشغيل: 0، 1، 0" in text


def test_stability_counts_and_lists_the_reports_whose_priority_changed():
    text = render_stability(*three_runs(second={2: answer(loc_number="355", urgency="critical")}))
    assert "بلاغات تغيّرت أولويتها بين التشغيلات: 1 من 3" in text
    assert "  - البلاغ 2: متوسط، حرج، متوسط (المتوقع: متوسط)" in text


def test_stability_says_zero_when_nothing_changed():
    text = render_stability(*three_runs())
    assert "بلاغات تغيّرت أولويتها بين التشغيلات: 0 من 3" in text
    assert "بلاغات تغيّر نوعها بين التشغيلات: 0 من 3" in text
    assert "بلاغات تغيّر مكانها (نوعه أو رقمه) بين التشغيلات: 0 من 3" in text
    assert "بلاغات تغيّرت إحالتها للمشرف بين التشغيلات: 0 من 3" in text
    assert "  - البلاغ" not in text


def test_a_priority_that_is_wrong_in_every_run_the_same_way_did_not_change():
    always = {1: answer(urgency="urgent")}
    runs, reports, table = three_runs(second=always, third=always)
    runs[0].results[1] = answer(urgency="urgent")
    assert "بلاغات تغيّرت أولويتها بين التشغيلات: 0 من 3" in render_stability(runs, reports, table)


def test_stability_counts_a_changed_type():
    text = render_stability(*three_runs(third={1: answer(type="ac")}))
    assert "بلاغات تغيّر نوعها بين التشغيلات: 1 من 3" in text
    assert "  - البلاغ 1: انقطاع الماء، انقطاع الماء، عطل تكييف (المتوقع: انقطاع الماء)" in text


def test_stability_counts_a_changed_place():
    text = render_stability(*three_runs(second={3: answer(loc_number="610")}, third={3: answer(loc_kind="floor", loc_number="6")}))
    assert "بلاغات تغيّر مكانها (نوعه أو رقمه) بين التشغيلات: 1 من 3" in text
    assert "  - البلاغ 3: غرفة 601، غرفة 610، دور 6 (المتوقع: غرفة 601)" in text


def test_stability_counts_a_changed_referral_to_the_supervisor():
    flagged = answer(needs_confirmation=True, reasons=("low_confidence",))
    text = render_stability(*three_runs(second={1: flagged}))
    assert "بلاغات تغيّرت إحالتها للمشرف بين التشغيلات: 1 من 3" in text
    assert "  - البلاغ 1: لا، نعم، لا (المتوقع: لا)" in text


def test_stability_leaves_out_the_expected_value_when_that_field_is_not_scored():
    runs, reports, table = three_runs(second={1: answer(urgency="urgent")})
    table[1] = expected(1, urgency=None)
    assert "  - البلاغ 1: متوسط، عاجل، متوسط\n" in render_stability(runs, reports, table)


def test_stability_only_compares_reports_that_every_run_read_and_says_so():
    runs, reports, table = three_runs()
    del runs[2].results[3]
    runs[2].stopped_at_cost_limit = True
    text = render_stability(runs, reports, table)
    assert "بلاغات تغيّرت أولويتها بين التشغيلات: 0 من 2" in text
    assert "تنبيه" in text


def test_stability_for_holdout_reports_is_titled_so():
    assert "(البلاغات المحجوبة)" in render_stability(*three_runs(), holdout=True)


def test_every_line_of_the_stability_section_starts_right_to_left():
    text = render_stability(*three_runs(second={2: answer(loc_number="355", urgency="critical")}))
    assert all(line.startswith("‏") for line in text.splitlines() if line)


# --- a wrong priority also says whether the model read the fault as partial -----


def test_a_wrong_priority_shows_that_the_model_read_the_fault_as_partial():
    read = answer(urgency="normal", partial=True, partial_words="بس شغال")
    text = render(run_of({1: read}), [sample(1)], {1: expected(1)})
    assert "الأولوية: المتوقع «متوسط»، الناتج «عادي» (لم يقرأ النموذج أي خطر، وقرأ أن العطل جزئي «بس شغال»)" in text


def test_the_partial_words_of_a_holdout_report_are_not_printed():
    wrong = {1: answer(urgency="normal", partial=True, partial_words="كلمات محجوبة"), 2: answer(type="ac"), 3: answer(loc_number="355")}
    text = render(run_of({1: answer()}), [sample(1)], {1: expected(1)}, holdout=a_holdout(wrong))
    assert "وقرأ أن العطل جزئي)" in holdout_part(text)
    assert "كلمات محجوبة" not in text


# --- stage 2: hotel, pilgrim's name, the question to the sender -----------------------------


def test_the_hotel_is_scored_when_the_expected_answers_give_one():
    reports = [sample(1), sample(2, minutes=30)]
    table = {1: expected(1, hotel="برج السكينة"), 2: expected(2, hotel="-")}
    results = {1: answer(hotel="دار المنارة"), 2: answer()}
    text = render(run_of(results), reports, table)
    assert "الفندق: الكل 1 من 2 (50%)" in text
    assert "الفندق: المتوقع «برج السكينة»، الناتج «دار المنارة»" in text


def test_the_hotel_is_right_when_it_is_the_same_hotel_in_another_spelling():
    table = {1: expected(1, hotel="فندق برج السكينه")}
    text = render(run_of({1: answer(hotel="برج السكينة")}), [sample(1)], table)
    assert "الفندق: الكل 1 من 1 (100%)" in text


def test_a_hotel_read_where_none_was_given_is_wrong():
    text = render(run_of({1: answer(hotel="برج السكينة")}), [sample(1)], {1: expected(1, hotel="-")})
    assert "الفندق: المتوقع «لا فندق»، الناتج «برج السكينة»" in text


def test_hotel_name_and_question_are_not_scored_when_the_expected_answers_leave_them_out():
    text = render(run_of({1: answer(hotel="برج السكينة", pilgrim_name="نبيل سعد")}), [sample(1)], {1: expected(1)})
    assert "الفندق: الكل لا يوجد" in text
    assert "اسم الحاج: الكل لا يوجد" in text
    assert "البلاغات الخاطئة: 0" in text


def test_the_pilgrims_name_is_scored_whatever_the_spelling_of_its_letters():
    reports = [sample(1), sample(2, minutes=30)]
    table = {1: expected(1, name="أحمد إدريس"), 2: expected(2, name="نبيل سعد")}
    results = {1: answer(pilgrim_name="احمد ادريس"), 2: answer(pilgrim_name=None)}
    text = render(run_of(results), reports, table)
    assert "اسم الحاج: الكل 1 من 2 (50%)" in text
    assert "اسم الحاج: المتوقع «نبيل سعد»، الناتج «لا اسم»" in text


def test_a_wrong_name_in_a_holdout_report_is_reported_without_any_name():
    wrong = {1: answer(pilgrim_name="زكريا الأول"), 2: answer(type="ac"), 3: answer(loc_number="355")}
    holdout = a_holdout(wrong)
    holdout.expected[1] = expected(1, name="زكريا الثاني")
    text = render(run_of({1: answer()}), [sample(1)], {1: expected(1)}, holdout=holdout)
    assert "اسم الحاج: لا يطابق المتوقع" in holdout_part(text)
    assert "زكريا" not in text


def test_the_question_to_the_sender_is_scored():
    no_room = answer(loc_kind="none", loc_number=None, needs_confirmation=True, reasons=("no_location",))
    reports = [sample(1), sample(2, minutes=30)]
    table = {
        1: expected(1, loc_kind="none", loc_number="-", needs_confirmation=True, ask="place"),
        2: expected(2, ask="place"),
    }
    text = render(run_of({1: no_room, 2: answer()}), reports, table)
    assert "السؤال للمرسل: الكل 1 من 2 (50%)" in text
    assert "السؤال للمرسل: المتوقع «الغرفة أو الدور»، الناتج «لا سؤال»" in text


def test_report_has_a_section_on_the_questions_to_senders():
    no_room = answer(loc_kind="none", loc_number=None, needs_confirmation=True, reasons=("no_location",))
    reports = [sample(1), sample(2, minutes=30), sample(3, minutes=60)]
    table = {
        1: expected(1, loc_kind="none", loc_number="-", needs_confirmation=True, ask="place"),
        2: expected(2, ask="-"),
        3: expected(3, ask="-"),
    }
    results = {1: no_room, 2: answer(), 3: no_room}
    section = render(run_of(results), reports, table).split("== سؤال المرسل ==")[1].split("\n\n")[0]
    assert "بلاغات يجب أن يُسأل مرسلها، وسُئل السؤال الصحيح: 1 من 1" in section
    assert "بلاغات سُئل مرسلها بلا داعٍ: 1" in section


# --- stage 2: messages that are not reports --------------------------------------------------


def chat_answer() -> Understanding:
    return answer(type="not_a_report", loc_kind="none", loc_number=None, owner="nobody", urgency="normal")


def chat_expected(id) -> Expected:
    return expected(id, type="not_a_report", loc_kind=None, loc_number=None, urgency=None, owner="nobody", incident=None)


def not_reports_section(text: str) -> str:
    return text.split("== الرسائل التي ليست بلاغات ==")[1].split("\n\n")[0]


def test_report_counts_the_non_reports_that_were_recognised():
    reports = [sample(1), sample(2, minutes=5), sample(3, minutes=9)]
    table = {1: expected(1), 2: chat_expected(2), 3: chat_expected(3)}
    results = {1: answer(), 2: chat_answer(), 3: answer(type="unclear", owner="supervisor", needs_confirmation=True, reasons=("unclear_type",))}
    section = not_reports_section(render(run_of(results), reports, table))
    assert "رسائل ليست بلاغات وعُرفت كذلك: 1 من 2" in section
    assert "رسائل ليست بلاغات وعُدّت بلاغاً: 1" in section
    assert "  - أرقامها: 3" in section
    assert "بلاغات حقيقية أُسقطت على أنها ليست بلاغاً: 0" in section


def test_a_real_report_dropped_as_a_non_report_is_counted_listed_and_a_confident_mistake():
    reports = [sample(1), sample(2, minutes=30)]
    table = {1: expected(1), 2: expected(2)}
    text = render(run_of({1: answer(), 2: chat_answer()}), reports, table)
    section = not_reports_section(text)
    assert "بلاغات حقيقية أُسقطت على أنها ليست بلاغاً: 1" in section
    assert "  - أرقامها: 2" in section
    assert "بلاغات فيها خطأ ولم تُحَل للمشرف: 1 من 2" in confident_section(text)


def test_messages_that_are_not_reports_do_not_count_as_incidents():
    reports = [sample(1), sample(2, minutes=5), sample(3, minutes=9)]
    table = {1: expected(1, incident=1), 2: chat_expected(2), 3: expected(3, incident=1)}
    section = grouping_section(render(run_of({1: answer(), 2: chat_answer(), 3: answer()}), reports, table))
    assert "عدد الحوادث: المتوقع 1، الناتج 1" in section
    assert "بلاغات في حادثتها الصحيحة: 2 من 2 (100%)" in section


def test_a_real_report_dropped_as_a_non_report_is_missing_from_its_incident():
    reports = [sample(1), sample(2, minutes=5)]
    table = {1: expected(1, incident=1), 2: expected(2, incident=1)}
    section = grouping_section(render(run_of({1: answer(), 2: chat_answer()}), reports, table))
    assert "بلاغات في حادثتها الصحيحة: 0 من 2 (0%)" in section
    assert "حوادث تفرّقت بلاغاتها (تكرار لم يُدمج): 1" in section


# --- stage 2: numbers that must never be printed ----------------------------------------------


def test_a_passport_or_visa_number_in_a_report_is_never_printed():
    text_with_numbers = "نبيل سعد ضيّع بطاقة نسك، جواز X0012345 وتأشيرة 9990001234"
    printed = render(run_of({1: answer(type="ac")}), [sample(1, text=text_with_numbers)], {1: expected(1)})
    assert "البلاغ 1" in printed and "نبيل سعد" in printed
    assert "X0012345" not in printed and "9990001234" not in printed
    assert "[رقم جواز]" in printed and "[رقم تأشيرة]" in printed
