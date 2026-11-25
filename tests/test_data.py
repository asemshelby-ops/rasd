"""Checks that the test reports and the expected-answer table are complete and consistent."""

from collections import Counter

from rasd.data import EXPECTED_STAGE, load_expected, load_reports
from rasd.routing import FAULT_TYPES, OWNER_BY_TYPE, priority_for
from rasd.schema import STAGES
from rasd.text import to_western_digits

REPORTS = load_reports()
EXPECTED = load_expected()


def test_there_are_50_arabic_and_8_urdu_messages():
    languages = Counter("ur" if r.lang == "ur" else "ar" for r in REPORTS)
    assert languages == {"ar": 50, "ur": 8}


def test_arabic_reports_cover_saudi_and_palestinian_dialects():
    dialects = {r.lang for r in REPORTS}
    assert {"ar-sa", "ar-ps"} <= dialects


def test_every_report_has_exactly_one_expected_answer():
    assert [r.id for r in REPORTS] == sorted(EXPECTED)


def test_reports_are_in_time_order():
    times = [r.sent_at for r in REPORTS]
    assert times == sorted(times)


def test_every_report_type_is_covered():
    types = {e.type for e in EXPECTED.values()}
    assert types == set(OWNER_BY_TYPE)


def test_at_least_10_reports_say_the_room_number_in_words():
    spoken = [e for e in EXPECTED.values() if e.room_in_words]
    assert len(spoken) >= 10


def test_reports_marked_as_spoken_do_not_contain_the_room_digits():
    by_id = {r.id: r for r in REPORTS}
    for e in EXPECTED.values():
        if e.room_in_words:
            text = to_western_digits(by_id[e.id].text)
            assert e.loc_number not in text, f"report {e.id} writes the room in digits"


def test_several_incidents_have_duplicate_reports():
    sizes = Counter(e.incident for e in EXPECTED.values() if e.incident is not None)
    assert sum(1 for n in sizes.values() if n > 1) >= 3


def test_expected_owner_follows_the_routing_table():
    for e in EXPECTED.values():
        assert e.owner == OWNER_BY_TYPE[e.type], f"report {e.id}"


def test_the_expected_answers_are_written_for_one_known_stage_of_the_journey():
    assert EXPECTED_STAGE in STAGES


def test_every_expected_answer_lists_the_risks_its_message_states():
    assert all(e.risks is not None for e in EXPECTED.values())


def test_expected_priority_follows_the_teams_table_and_the_stated_risks():
    """The expected priority is never typed by hand: it is what routing.priority_for
    gives for the type and the risks written next to it."""
    for e in EXPECTED.values():
        if e.urgency is not None:
            assert e.urgency == priority_for(e.type, e.risks, EXPECTED_STAGE, e.partial), f"report {e.id}"


def test_some_expected_answers_are_partial_faults_and_only_faults_are_partial():
    partial = [e for e in EXPECTED.values() if e.partial]
    assert len(partial) >= 2
    assert all(e.type in FAULT_TYPES for e in partial)


def test_the_expected_answers_use_every_priority_level_and_every_kind_of_risk():
    from rasd.schema import RISKS, URGENCIES

    assert {e.urgency for e in EXPECTED.values() if e.urgency} == set(URGENCIES)
    assert {risk for e in EXPECTED.values() for risk in e.risks} == set(RISKS)


def test_some_reports_are_expected_to_need_supervisor_confirmation():
    flagged = [e for e in EXPECTED.values() if e.needs_confirmation is True]
    assert len(flagged) >= 3


# --- the owner's holdout folder --------------------------------------------
# These tests write their own small files. They never open data/holdout itself:
# what the owner writes there is only read by benchmark.py when it runs.

import pytest

from rasd.data import load_holdout

REPORTS_HEAD = "id,sent_at,lang,text\n"
EXPECTED_HEAD = "id,type,loc_kind,loc_number,urgency,owner,incident,needs_confirmation,room_in_words,note\n"
SECRET = "نص سري لا يظهر في رسائل الخطأ"


def holdout_folder(tmp_path, reports: str, expected: str):
    (tmp_path / "reports.csv").write_text(REPORTS_HEAD + reports, encoding="utf-8-sig")
    (tmp_path / "expected.csv").write_text(EXPECTED_HEAD + expected, encoding="utf-8-sig")
    return tmp_path


def test_there_is_no_holdout_when_the_folder_is_missing(tmp_path):
    assert load_holdout(tmp_path / "nothing-here") is None


def test_there_is_no_holdout_when_the_files_have_only_their_header_row(tmp_path):
    assert load_holdout(holdout_folder(tmp_path, "", "")) is None


def test_holdout_reports_and_expected_answers_are_loaded(tmp_path):
    folder = holdout_folder(
        tmp_path,
        f'1,2026-12-23 09:15,ar-sa,"{SECRET}"\n2,2026-12-23 09:20,ur,"{SECRET}"\n',
        "1,water,room,907,medium,maintenance,1,0,1,\n2,unclear,none,-,,supervisor,2,1,0,\n",
    )
    reports, expected = load_holdout(folder)
    assert [(r.id, r.lang, r.text) for r in reports] == [(1, "ar-sa", SECRET), (2, "ur", SECRET)]
    assert reports[0].sent_at.hour == 9 and reports[0].sent_at.minute == 15
    assert (expected[1].type, expected[1].loc_number, expected[1].room_in_words) == ("water", "907", True)
    assert (expected[2].urgency, expected[2].needs_confirmation) == (None, True)


def test_holdout_reports_and_answers_must_have_the_same_report_numbers(tmp_path):
    folder = holdout_folder(
        tmp_path,
        f'1,2026-12-23 09:15,ar-sa,"{SECRET}"\n2,2026-12-23 09:20,ar-sa,"{SECRET}"\n',
        "1,water,room,907,medium,maintenance,1,0,0,\n3,water,room,355,medium,maintenance,2,0,0,\n",
    )
    with pytest.raises(ValueError) as problem:
        load_holdout(folder)
    assert "2" in str(problem.value) and "3" in str(problem.value)
    assert SECRET not in str(problem.value)


def test_blank_rows_left_by_excel_are_ignored(tmp_path):
    folder = holdout_folder(
        tmp_path,
        f'1,2026-12-23 09:15,ar-sa,"{SECRET}"\n,,,\n',
        "1,water,room,907,medium,maintenance,1,0,0,\n,,,,,,,,,\n",
    )
    reports, expected = load_holdout(folder)
    assert len(reports) == 1 and list(expected) == [1]


def test_a_time_with_seconds_is_accepted(tmp_path):
    folder = holdout_folder(
        tmp_path, f'1,2026-12-23 09:15:00,ar-sa,"{SECRET}"\n', "1,water,room,907,medium,maintenance,1,0,0,\n"
    )
    reports, _ = load_holdout(folder)
    assert reports[0].sent_at.minute == 15


def test_a_time_that_excel_rewrote_is_reported_with_the_report_number(tmp_path):
    folder = holdout_folder(
        tmp_path, f'7,23/12/2026 9:15,ar-sa,"{SECRET}"\n', "7,water,room,907,medium,maintenance,1,0,0,\n"
    )
    with pytest.raises(ValueError) as problem:
        load_holdout(folder)
    message = str(problem.value)
    assert "reports.csv" in message and "report 7" in message and "2026-12-22 08:02" in message
    assert SECRET not in message


def test_an_empty_incident_cell_means_grouping_is_not_scored(tmp_path):
    folder = holdout_folder(
        tmp_path, f'1,2026-12-23 09:15,ar-sa,"{SECRET}"\n', "1,water,room,907,medium,maintenance,,0,0,\n"
    )
    _, expected = load_holdout(folder)
    assert expected[1].incident is None


def test_arabic_digits_in_the_expected_room_number_are_read_as_western_digits(tmp_path):
    folder = holdout_folder(
        tmp_path, f'1,2026-12-23 09:15,ar-sa,"{SECRET}"\n', "1,water,room,٩٠٧,medium,maintenance,1,0,0,\n"
    )
    _, expected = load_holdout(folder)
    assert expected[1].loc_number == "907"


def test_a_missing_column_is_named(tmp_path):
    (tmp_path / "reports.csv").write_text(f'id,sent_at,text\n1,2026-12-23 09:15,"{SECRET}"\n', encoding="utf-8-sig")
    (tmp_path / "expected.csv").write_text(
        EXPECTED_HEAD + "1,water,room,907,medium,maintenance,1,0,0,\n", encoding="utf-8-sig"
    )
    with pytest.raises(ValueError) as problem:
        load_holdout(tmp_path)
    assert "reports.csv" in str(problem.value) and "lang" in str(problem.value)
    assert SECRET not in str(problem.value)


def test_the_note_column_may_be_left_out(tmp_path):
    (tmp_path / "reports.csv").write_text(REPORTS_HEAD + f'1,2026-12-23 09:15,ar-sa,"{SECRET}"\n', encoding="utf-8-sig")
    (tmp_path / "expected.csv").write_text(
        "id,type,loc_kind,loc_number,urgency,owner,incident,needs_confirmation,room_in_words\n"
        "1,water,room,907,medium,maintenance,1,0,0\n",
        encoding="utf-8-sig",
    )
    _, expected = load_holdout(tmp_path)
    assert expected[1].note == ""


@pytest.mark.parametrize(
    "row, word",
    [
        ("1,leak,room,907,medium,maintenance,1,0,0,", "type"),
        ("1,water,rooom,907,medium,maintenance,1,0,0,", "loc_kind"),
        ("1,water,room,907,soon,maintenance,1,0,0,", "urgency"),
        ("1,water,room,907,medium,plumber,1,0,0,", "owner"),
        ("1,water,room,,medium,maintenance,1,0,0,", "loc_number"),
        ("1,water,room,nine,medium,maintenance,1,0,0,", "loc_number"),
        ("1,water,room,907,medium,maintenance,first,0,0,", "incident"),
        ("1,water,room,907,medium,maintenance,1,yes,0,", "needs_confirmation"),
        ("1,water,room,907,medium,maintenance,1,0,yes,", "room_in_words"),
    ],
)
def test_a_wrong_cell_in_the_expected_answers_names_the_file_the_report_and_the_column(tmp_path, row, word):
    folder = holdout_folder(tmp_path, f'1,2026-12-23 09:15,ar-sa,"{SECRET}"\n', row + "\n")
    with pytest.raises(ValueError) as problem:
        load_holdout(folder)
    message = str(problem.value)
    assert "expected.csv" in message and "report 1" in message and word in message


def test_a_report_number_used_twice_is_an_error(tmp_path):
    folder = holdout_folder(
        tmp_path,
        f'1,2026-12-23 09:15,ar-sa,"{SECRET}"\n1,2026-12-23 09:20,ar-sa,"{SECRET}"\n',
        "1,water,room,907,medium,maintenance,1,0,0,\n",
    )
    with pytest.raises(ValueError, match="more than once"):
        load_holdout(folder)


def test_a_report_number_that_is_not_a_number_is_an_error(tmp_path):
    folder = holdout_folder(
        tmp_path, f'A,2026-12-23 09:15,ar-sa,"{SECRET}"\n', "A,water,room,907,medium,maintenance,1,0,0,\n"
    )
    with pytest.raises(ValueError, match="id"):
        load_holdout(folder)


def test_an_unknown_language_is_an_error(tmp_path):
    folder = holdout_folder(
        tmp_path, f'1,2026-12-23 09:15,english,"{SECRET}"\n', "1,water,room,907,medium,maintenance,1,0,0,\n"
    )
    with pytest.raises(ValueError) as problem:
        load_holdout(folder)
    assert "lang" in str(problem.value) and "report 1" in str(problem.value)
    assert SECRET not in str(problem.value)


def test_a_report_with_no_text_is_an_error(tmp_path):
    folder = holdout_folder(tmp_path, "1,2026-12-23 09:15,ar-sa,\n", "1,water,room,907,medium,maintenance,1,0,0,\n")
    with pytest.raises(ValueError, match="text"):
        load_holdout(folder)


def test_reports_without_an_expected_file_are_an_error(tmp_path):
    (tmp_path / "reports.csv").write_text(REPORTS_HEAD + f'1,2026-12-23 09:15,ar-sa,"{SECRET}"\n', encoding="utf-8-sig")
    with pytest.raises(ValueError, match="expected.csv"):
        load_holdout(tmp_path)


# --- the optional risks column -----------------------------------------------

RISKS_HEAD = "id,type,loc_kind,loc_number,urgency,owner,incident,needs_confirmation,room_in_words,risks,note\n"


def expected_with_risks(tmp_path, row: str):
    (tmp_path / "reports.csv").write_text(REPORTS_HEAD + f'1,2026-12-23 09:15,ar-sa,"{SECRET}"\n', encoding="utf-8-sig")
    (tmp_path / "expected.csv").write_text(RISKS_HEAD + row + "\n", encoding="utf-8-sig")
    return load_holdout(tmp_path)[1][1]


def test_risks_are_read_as_a_list_of_codes(tmp_path):
    expected = expected_with_risks(tmp_path, "1,cleaning,room,907,urgent,housekeeping,1,0,0,elderly sick,")
    assert expected.risks == ("elderly", "sick")


def test_an_empty_risks_cell_means_the_message_states_no_risk(tmp_path):
    expected = expected_with_risks(tmp_path, "1,cleaning,room,907,normal,housekeeping,1,0,0,,")
    assert expected.risks == ()


def test_a_file_without_a_risks_column_has_no_risk_information(tmp_path):
    folder = holdout_folder(
        tmp_path, f'1,2026-12-23 09:15,ar-sa,"{SECRET}"\n', "1,water,room,907,urgent,maintenance,1,0,0,\n"
    )
    assert load_holdout(folder)[1][1].risks is None


def test_a_risk_that_does_not_exist_names_the_file_the_report_and_the_column(tmp_path):
    with pytest.raises(ValueError) as problem:
        expected_with_risks(tmp_path, "1,cleaning,room,907,medium,housekeeping,1,0,0,angry,")
    message = str(problem.value)
    assert "expected.csv" in message and "report 1" in message and "risks" in message


def test_the_new_priority_levels_are_accepted_and_the_old_lowest_level_is_not(tmp_path):
    assert expected_with_risks(tmp_path, "1,health,room,907,critical,pilgrim_affairs,1,0,0,,").urgency == "critical"
    assert expected_with_risks(tmp_path, "1,cleaning,room,907,normal,housekeeping,1,0,0,,").urgency == "normal"
    with pytest.raises(ValueError, match="urgency"):
        expected_with_risks(tmp_path, "1,cleaning,room,907,low,housekeeping,1,0,0,,")


# --- the optional partial column ----------------------------------------------

PARTIAL_HEAD = "id,type,loc_kind,loc_number,urgency,owner,incident,needs_confirmation,room_in_words,risks,partial,note\n"


def expected_with_partial(tmp_path, row: str):
    (tmp_path / "reports.csv").write_text(REPORTS_HEAD + f'1,2026-12-23 09:15,ar-sa,"{SECRET}"\n', encoding="utf-8-sig")
    (tmp_path / "expected.csv").write_text(PARTIAL_HEAD + row + "\n", encoding="utf-8-sig")
    return load_holdout(tmp_path)[1][1]


def test_partial_is_read_from_its_column(tmp_path):
    assert expected_with_partial(tmp_path, "1,ac,room,907,medium,maintenance,1,0,0,,1,").partial is True
    assert expected_with_partial(tmp_path, "1,ac,room,907,urgent,maintenance,1,0,0,,0,").partial is False
    assert expected_with_partial(tmp_path, "1,ac,room,907,urgent,maintenance,1,0,0,,,").partial is False


def test_a_file_without_a_partial_column_has_no_partial_faults(tmp_path):
    assert expected_with_risks(tmp_path, "1,ac,room,907,urgent,maintenance,1,0,0,,").partial is False


def test_a_wrong_value_in_the_partial_column_names_the_file_the_report_and_the_column(tmp_path):
    with pytest.raises(ValueError) as problem:
        expected_with_partial(tmp_path, "1,ac,room,907,medium,maintenance,1,0,0,,half,")
    message = str(problem.value)
    assert "expected.csv" in message and "report 1" in message and "partial" in message


# --- stage 2 columns: photo, hotel, name, ask --------------------------------------------

STYLE_HEAD = "id,type,loc_kind,loc_number,urgency,owner,incident,needs_confirmation,room_in_words,hotel,name,ask,note\n"


def real_style(tmp_path, report_row: str, expected_row: str, reports_head="id,sent_at,lang,text,photo\n"):
    (tmp_path / "reports.csv").write_text(reports_head + report_row + "\n", encoding="utf-8-sig")
    (tmp_path / "expected.csv").write_text(STYLE_HEAD + expected_row + "\n", encoding="utf-8-sig")
    reports, expected = load_holdout(tmp_path)
    return reports[0], expected[1]


def test_the_photo_column_says_a_photo_came_with_the_message(tmp_path):
    report, _ = real_style(tmp_path, f'1,2026-12-23 09:15,ar-sa,"{SECRET}",1', "1,nusuk_card,none,-,urgent,pilgrim_affairs,1,0,0,برج السكينة,نبيل سعد,-,")
    assert report.photo is True


def test_a_message_may_be_a_photo_with_no_words(tmp_path):
    report, _ = real_style(tmp_path, "1,2026-12-23 09:15,ar-sa,,1", "1,unclear,none,-,,supervisor,1,1,0,-,-,type,")
    assert (report.text, report.photo) == ("", True)


def test_a_message_with_no_words_and_no_photo_is_still_an_error(tmp_path):
    with pytest.raises(ValueError, match="text"):
        real_style(tmp_path, "1,2026-12-23 09:15,ar-sa,,0", "1,unclear,none,-,,supervisor,1,1,0,-,-,type,")


def test_a_file_without_a_photo_column_has_no_photos(tmp_path):
    report, _ = real_style(
        tmp_path, f'1,2026-12-23 09:15,ar-sa,"{SECRET}"', "1,water,room,907,urgent,maintenance,1,0,0,-,-,-,",
        reports_head=REPORTS_HEAD,
    )  # fmt: skip
    assert report.photo is False


def test_hotel_name_and_ask_are_read(tmp_path):
    _, expected = real_style(tmp_path, f'1,2026-12-23 09:15,ar-sa,"{SECRET}",0', "1,nusuk_card,none,-,urgent,pilgrim_affairs,1,1,0,برج السكينة,-,name,")
    assert (expected.hotel, expected.name, expected.ask) == ("برج السكينة", "-", "name")


def test_empty_hotel_name_and_ask_cells_are_not_scored(tmp_path):
    _, expected = real_style(tmp_path, f'1,2026-12-23 09:15,ar-sa,"{SECRET}",0', "1,water,room,907,urgent,maintenance,1,0,0,,,,")
    assert (expected.hotel, expected.name, expected.ask) == (None, None, None)


def test_a_file_without_those_columns_does_not_score_them(tmp_path):
    folder = holdout_folder(tmp_path, f'1,2026-12-23 09:15,ar-sa,"{SECRET}"\n', "1,water,room,907,urgent,maintenance,1,0,0,\n")
    expected = load_holdout(folder)[1][1]
    assert (expected.hotel, expected.name, expected.ask) == (None, None, None)


def test_a_wrong_value_in_the_ask_column_names_the_file_the_report_and_the_column(tmp_path):
    with pytest.raises(ValueError) as problem:
        real_style(tmp_path, f'1,2026-12-23 09:15,ar-sa,"{SECRET}",0', "1,water,none,-,urgent,maintenance,1,1,0,-,-,room,")
    message = str(problem.value)
    assert "expected.csv" in message and "report 1" in message and "ask" in message


def test_a_message_that_is_not_a_report_is_accepted_with_its_owner_nobody(tmp_path):
    _, expected = real_style(tmp_path, f'1,2026-12-23 09:15,ar-sa,"{SECRET}",0', "1,not_a_report,,,,nobody,,0,0,-,-,-,")
    assert (expected.type, expected.owner, expected.incident) == ("not_a_report", "nobody", None)


# --- the main data follows the team's rules, not hand-typed answers -----------------------


def test_the_main_set_has_real_style_reports_and_messages_that_are_not_reports():
    assert sum(1 for e in EXPECTED.values() if e.type == "not_a_report") >= 6
    assert sum(1 for e in EXPECTED.values() if e.hotel not in (None, "-")) >= 8
    assert sum(1 for e in EXPECTED.values() if e.name not in (None, "-")) >= 5
    assert any(r.photo for r in REPORTS)
    assert {e.ask for e in EXPECTED.values()} >= {"type", "place", "name", "-"}


def test_expected_supervisor_flag_follows_what_each_type_needs():
    from rasd.understand import requirement_reasons

    for e in EXPECTED.values():
        if e.loc_kind is None or e.needs_confirmation is None or e.hotel is None or e.name is None:
            continue
        number = None if e.loc_number == "-" else e.loc_number
        hotel = None if e.hotel == "-" else e.hotel
        name = None if e.name == "-" else e.name
        needs = bool(requirement_reasons(e.type, hotel, e.loc_kind, number, name))
        assert e.needs_confirmation == needs, f"report {e.id}"


def test_every_new_type_and_every_non_report_has_the_owner_from_the_table():
    for e in EXPECTED.values():
        assert e.owner == OWNER_BY_TYPE[e.type], f"report {e.id}"
