"""Checks that the test reports and the expected-answer table are complete and consistent."""

from collections import Counter

from rasd.data import load_expected, load_reports
from rasd.routing import OWNER_BY_TYPE
from rasd.text import to_western_digits

REPORTS = load_reports()
EXPECTED = load_expected()


def test_there_are_30_arabic_and_5_urdu_reports():
    languages = Counter("ur" if r.lang == "ur" else "ar" for r in REPORTS)
    assert languages == {"ar": 30, "ur": 5}


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
    sizes = Counter(e.incident for e in EXPECTED.values())
    assert sum(1 for n in sizes.values() if n > 1) >= 3


def test_expected_owner_follows_the_routing_table():
    for e in EXPECTED.values():
        assert e.owner == OWNER_BY_TYPE[e.type], f"report {e.id}"


def test_some_reports_are_expected_to_need_supervisor_confirmation():
    flagged = [e for e in EXPECTED.values() if e.needs_confirmation is True]
    assert len(flagged) >= 3
