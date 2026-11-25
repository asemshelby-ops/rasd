"""Duplicate merging: messages about the same problem in the same place become one incident.

The rooms and times here are made up for these tests.
"""

from datetime import datetime, timedelta

from rasd.data import load_expected, load_reports
from rasd.incidents import MERGE_WINDOW_MINUTES, add_report, group_reports
from rasd.routing import DEADLINE_MINUTES
from rasd.understand import Understanding

START = datetime(2026, 12, 22, 8, 0)


def report(**changes) -> Understanding:
    """A clear report: water fault in room 907. Tests change one field at a time."""
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
    )
    fields.update(changes)
    return Understanding(**fields)


def arrivals(*items):
    """Each item is (minutes after START, report). Report ids are 1, 2, 3... in the order given."""
    return [(i, START + timedelta(minutes=minutes), r) for i, (minutes, r) in enumerate(items, start=1)]


def grouped(*items, **options) -> list[list[int]]:
    return [incident.report_ids for incident in group_reports(arrivals(*items), **options)]


# --- what merges ----------------------------------------------------------


def test_same_type_and_same_room_close_in_time_become_one_incident():
    incidents = group_reports(arrivals((0, report()), (10, report())))
    assert len(incidents) == 1
    assert incidents[0].report_ids == [1, 2]
    assert incidents[0].message_count == 2


def test_the_incident_keeps_the_type_and_the_place():
    incident = group_reports(arrivals((0, report()), (10, report())))[0]
    assert (incident.type, incident.loc_kind, incident.loc_number) == ("water", "room", "907")


def test_the_incident_remembers_its_first_and_last_message_times():
    incident = group_reports(arrivals((0, report()), (10, report()), (25, report())))[0]
    assert incident.first_at == START
    assert incident.last_at == START + timedelta(minutes=25)


def test_an_elevator_reported_twice_is_one_incident():
    stuck = report(type="power_elevator", loc_kind="elevator", loc_number="7", urgency="urgent")
    assert grouped((0, stuck), (3, stuck)) == [[1, 2]]


def test_a_floor_reported_twice_is_one_incident():
    dry = report(loc_kind="floor", loc_number="9", urgency="urgent")
    assert grouped((0, dry), (8, dry)) == [[1, 2]]


def test_a_single_message_is_an_incident_of_one():
    incidents = group_reports(arrivals((0, report())))
    assert [i.report_ids for i in incidents] == [[1]]
    assert incidents[0].message_count == 1


# --- what stays separate --------------------------------------------------


def test_different_rooms_are_different_incidents():
    assert grouped((0, report()), (5, report(loc_number="355"))) == [[1], [2]]


def test_different_types_in_the_same_room_are_different_incidents():
    assert grouped((0, report()), (5, report(type="cleaning", owner="housekeeping"))) == [[1], [2]]


def test_the_same_number_on_a_room_a_floor_and_an_elevator_is_three_places():
    seven = dict(type="power_elevator", loc_number="7")
    result = grouped(
        (0, report(loc_kind="room", **seven)),
        (1, report(loc_kind="floor", **seven)),
        (2, report(loc_kind="elevator", **seven)),
    )
    assert result == [[1], [2], [3]]


def test_messages_about_other_places_in_between_do_not_break_an_incident():
    assert grouped((0, report()), (5, report(loc_number="355")), (10, report())) == [[1, 3], [2]]


# --- the time window ------------------------------------------------------


def test_the_same_problem_long_after_the_window_is_a_new_incident():
    assert grouped((0, report()), (MERGE_WINDOW_MINUTES + 120, report())) == [[1], [2]]


def test_a_message_exactly_at_the_end_of_the_window_still_merges():
    assert grouped((0, report()), (MERGE_WINDOW_MINUTES, report())) == [[1, 2]]


def test_a_message_one_minute_after_the_window_does_not_merge():
    assert grouped((0, report()), (MERGE_WINDOW_MINUTES + 1, report())) == [[1], [2]]


def test_the_window_is_counted_from_the_latest_message_of_the_incident():
    # 0, 40 and 80 minutes with a 60 minute window: each is within 60 of the one before it.
    assert grouped((0, report()), (40, report()), (80, report()), window_minutes=60) == [[1, 2, 3]]


def test_the_window_can_be_changed():
    assert grouped((0, report()), (15, report()), window_minutes=10) == [[1], [2]]
    assert grouped((0, report()), (15, report()), window_minutes=20) == [[1, 2]]


def test_after_the_window_a_new_incident_collects_the_later_messages():
    late = MERGE_WINDOW_MINUTES + 120
    assert grouped((0, report()), (5, report()), (late, report()), (late + 5, report())) == [[1, 2], [3, 4]]


# --- what never merges ----------------------------------------------------


def test_reports_with_no_location_never_merge():
    lost = report(type="ac", loc_kind="none", loc_number=None, needs_confirmation=True, reasons=("no_location",))
    assert grouped((0, lost), (2, lost)) == [[1], [2]]


def test_a_room_without_its_number_never_merges():
    no_number = report(loc_number=None, needs_confirmation=True, reasons=("no_location",))
    assert grouped((0, no_number), (2, no_number)) == [[1], [2]]


def test_reports_with_an_unclear_type_never_merge():
    vague = report(type="unclear", owner="supervisor", needs_confirmation=True, reasons=("unclear_type",))
    assert grouped((0, vague), (2, vague)) == [[1], [2]]


def test_an_unclear_type_never_merges_even_when_nobody_is_asked_to_confirm_it():
    # Two unknown problems in the same room may be two different problems.
    vague = report(type="unclear", owner="supervisor", needs_confirmation=False)
    assert grouped((0, vague), (2, vague)) == [[1], [2]]


def test_a_common_area_never_merges_because_we_do_not_know_which_one_it_is():
    lobby = report(type="cleaning", loc_kind="common_area", loc_number=None, owner="housekeeping")
    assert grouped((0, lobby), (2, lobby)) == [[1], [2]]


def test_a_report_waiting_for_the_supervisor_never_merges_on_its_own():
    unsure = report(needs_confirmation=True, reasons=("number_not_confirmed",))
    assert grouped((0, report()), (5, unsure)) == [[1], [2]]


def test_nothing_merges_into_a_report_that_is_waiting_for_the_supervisor():
    unsure = report(needs_confirmation=True, reasons=("low_confidence",))
    assert grouped((0, unsure), (5, report()), (9, report())) == [[1], [2, 3]]


def test_a_report_the_model_could_not_read_never_merges():
    unread = report(
        type="unclear", loc_kind="none", loc_number=None, urgency="urgent", owner="supervisor",
        confidence="low", needs_confirmation=True, reasons=("not_understood",),
    )
    assert grouped((0, unread), (1, unread)) == [[1], [2]]


# --- closed incidents -------------------------------------------------------


def after(minutes: int) -> datetime:
    return START + timedelta(minutes=minutes)


def test_a_new_incident_is_open():
    assert group_reports(arrivals((0, report())))[0].closed_at is None


def test_a_report_about_a_closed_incident_opens_a_new_incident():
    incidents = group_reports(arrivals((0, report())))
    incidents[0].closed_at = after(10)

    # Same problem, same room, well inside the merging window: but the first incident is closed.
    new = add_report(incidents, 2, after(20), report())

    assert [i.report_ids for i in incidents] == [[1], [2]]
    assert new is incidents[1]
    assert new.closed_at is None


def test_a_closed_incident_is_left_exactly_as_it_was():
    incidents = group_reports(arrivals((0, report()), (5, report())))
    incidents[0].closed_at = after(10)
    add_report(incidents, 3, after(20), report(urgency="urgent"))
    closed = incidents[0]
    assert closed.report_ids == [1, 2]
    assert closed.last_at == after(5)
    assert closed.urgency == "medium"


def test_later_reports_join_the_new_incident_and_not_the_closed_one():
    incidents = group_reports(arrivals((0, report())))
    incidents[0].closed_at = after(10)
    add_report(incidents, 2, after(20), report())
    add_report(incidents, 3, after(25), report())
    assert [i.report_ids for i in incidents] == [[1], [2, 3]]


def test_closing_one_incident_does_not_stop_merging_in_another_room():
    incidents = group_reports(arrivals((0, report()), (1, report(loc_number="355"))))
    incidents[0].closed_at = after(10)
    add_report(incidents, 3, after(20), report(loc_number="355"))
    assert [i.report_ids for i in incidents] == [[1], [2, 3]]


# --- adding one report at a time, as the live system will ----------------------


def test_the_first_report_starts_the_first_incident():
    incidents = []
    first = add_report(incidents, 1, START, report())
    assert incidents == [first]
    assert first.report_ids == [1]


def test_a_report_added_later_joins_the_open_incident_and_that_incident_is_returned():
    incidents = []
    first = add_report(incidents, 1, START, report())
    second = add_report(incidents, 2, after(5), report())
    assert second is first
    assert first.report_ids == [1, 2]
    assert len(incidents) == 1


def test_adding_one_at_a_time_gives_the_same_incidents_as_grouping_all_at_once():
    items = arrivals((0, report()), (3, report(loc_number="355")), (9, report()), (200, report()))
    one_by_one = []
    for report_id, sent_at, r in items:
        add_report(one_by_one, report_id, sent_at, r)
    assert [i.report_ids for i in one_by_one] == [i.report_ids for i in group_reports(items)]


def test_the_window_can_be_changed_when_adding_one_report():
    incidents = []
    add_report(incidents, 1, START, report(), window_minutes=10)
    add_report(incidents, 2, after(15), report(), window_minutes=10)
    assert [i.report_ids for i in incidents] == [[1], [2]]


# --- the incident as a whole ----------------------------------------------


def test_the_incident_is_as_urgent_as_its_most_urgent_message():
    incident = group_reports(arrivals((0, report(urgency="low")), (5, report(urgency="urgent")), (9, report())))[0]
    assert incident.urgency == "urgent"


def test_every_urgency_code_can_be_ranked():
    for urgency in DEADLINE_MINUTES:
        assert group_reports(arrivals((0, report(urgency=urgency))))[0].urgency == urgency


def test_messages_are_handled_in_the_order_they_were_sent():
    out_of_order = [
        (1, START + timedelta(minutes=30), report()),
        (2, START, report()),
        (3, START + timedelta(minutes=10), report(loc_number="355")),
    ]
    incidents = group_reports(out_of_order)
    assert [i.report_ids for i in incidents] == [[2, 1], [3]]


def test_every_report_lands_in_exactly_one_incident():
    items = [(m, report(loc_number=str(900 + m % 3))) for m in range(0, 40, 4)]
    incidents = group_reports(arrivals(*items))
    ids = sorted(rid for incident in incidents for rid in incident.report_ids)
    assert ids == list(range(1, len(items) + 1))


def test_no_reports_means_no_incidents():
    assert group_reports([]) == []


# --- the benchmark's expected table follows the same rule -----------------


def test_with_perfect_understanding_the_rule_reproduces_the_expected_incidents():
    """If every report were understood exactly as data/expected.csv says, merging
    would give exactly the incident column of that table."""
    expected = load_expected()
    perfect = []
    for r in load_reports():
        e = expected[r.id]
        number = e.loc_number if e.loc_number not in (None, "-") else None
        perfect.append(
            (r.id, r.sent_at, report(
                type=e.type,
                loc_kind=e.loc_kind or "room",  # location not scored: a room whose number is unknown
                loc_number=number,
                urgency=e.urgency or "medium",
                owner=e.owner,
                needs_confirmation=bool(e.needs_confirmation),
            ))
        )
    produced = sorted(sorted(i.report_ids) for i in group_reports(perfect))

    by_incident = {}
    for e in expected.values():
        by_incident.setdefault(e.incident, []).append(e.id)
    assert produced == sorted(sorted(ids) for ids in by_incident.values())
