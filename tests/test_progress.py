"""Progress steps on every case: received, assigned to its owner, in progress, closed.

The board shows them on each card, and the sender sees them under their own report.
No AI model and no network. Everything is invented.
"""

import re
import sqlite3
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app import copy
from app.main import create_app
from rasd.elm import SimulatedElm
from rasd.understand import Reading, build_report

HOTEL = "برج السكينة"
KEYS = ["received", "assigned", "in_progress", "closed"]


def reading(**fields) -> Reading:
    base = dict(
        type="water", hotel="", location_kind="room", number_words="907", location_number="907", pilgrim_name="",
        risks=[], partial_words="", confidence="high",
    )  # fmt: skip
    base.update(fields)
    return Reading(**base)


NO_PLACE = dict(location_kind="room", number_words="", location_number="")
WITH_ROOM = "ما في موية في غرفة 907"


class Engine:
    def __init__(self):
        self.elm, self.readings = SimulatedElm(), {}

    def read(self, text, photo_attached=False):
        return build_report(text, self.readings.get(text, reading()), photo_attached=photo_attached)


class Clock:
    def __init__(self):
        self.now = datetime(2026, 12, 23, 10, 0, 0)

    def __call__(self):
        return self.now


@pytest.fixture
def site(tmp_path):
    engine, clock = Engine(), Clock()
    client = TestClient(create_app(engine=engine, db_path=tmp_path / "rasd.db", now=clock))
    client.engine, client.clock, client.db = engine, clock, tmp_path / "rasd.db"
    return client


def send(site, text, hotel=HOTEL):
    return site.post("/api/reports", data={"text": text, "hotel": hotel}).json()


def case(site, number=1):
    return next(c for c in site.get("/api/board").json()["cases"] if c["id"] == number)


def states(steps):
    return [step["state"] for step in steps]


def record(site, number=1):
    return site.get(f"/api/cases/{number}/steps").json()["steps"]


def waiting_report(site):
    site.engine.readings["الموية مقطوعة عندنا"] = reading(**NO_PLACE)
    return send(site, "الموية مقطوعة عندنا")


# --- the four steps and which one is the current one ---------------------------------------------------


def test_the_step_labels_are_in_the_copy_file_in_order():
    assert list(copy.STEPS) == KEYS and all(copy.STEPS.values())


def test_a_complete_report_is_received_and_assigned_at_once(site):
    send(site, WITH_ROOM)
    steps = case(site)["steps"]
    assert [step["key"] for step in steps] == KEYS
    assert [step["label"] for step in steps] == list(copy.STEPS.values())
    assert states(steps) == ["done", "current", "todo", "todo"]


def test_a_report_that_waits_for_the_supervisor_is_only_received(site):
    waiting_report(site)
    assert states(case(site)["steps"]) == ["current", "todo", "todo", "todo"]


def test_confirming_assigns_it_and_records_who_and_when(site):
    waiting_report(site)
    site.clock.now += timedelta(minutes=3)
    site.post("/api/cases/1/confirm", data={"who": "سالم"})
    assert states(case(site)["steps"]) == ["done", "current", "todo", "todo"]
    assert record(site) == [
        {"step": "received", "at": "2026-12-23T10:00:00", "who": copy.STEP_BY_SENDER, "skipped": False},
        {"step": "assigned", "at": "2026-12-23T10:03:00", "who": "سالم", "skipped": False},
    ]


def test_an_answer_that_completes_the_report_assigns_it(site):
    reply = waiting_report(site)
    site.clock.now += timedelta(minutes=2)
    site.post(f"/api/reports/{reply['report_id']}/answer", data={"reply": "512"})
    assert states(case(site)["steps"]) == ["done", "current", "todo", "todo"]
    assert record(site)[1] == {"step": "assigned", "at": "2026-12-23T10:02:00", "who": copy.STEP_BY_RASD, "skipped": False}


def test_a_report_assigned_on_arrival_is_assigned_by_rasd(site):
    send(site, WITH_ROOM)
    assert record(site)[1] == {"step": "assigned", "at": "2026-12-23T10:00:00", "who": copy.STEP_BY_RASD, "skipped": False}


def test_acknowledging_puts_it_in_progress_once(site):
    send(site, WITH_ROOM)
    site.clock.now += timedelta(minutes=4)
    site.post("/api/cases/1/acknowledge", data={"who": "هشام"})
    site.clock.now += timedelta(minutes=4)
    site.post("/api/cases/1/acknowledge", data={"who": "سالم"})
    assert states(case(site)["steps"]) == ["done", "done", "current", "todo"]
    assert record(site)[2] == {"step": "in_progress", "at": "2026-12-23T10:04:00", "who": "هشام", "skipped": False}


def test_closing_is_the_last_step_with_who_and_when(site):
    send(site, WITH_ROOM)
    site.post("/api/cases/1/acknowledge", data={"who": "هشام"})
    site.clock.now += timedelta(minutes=9)
    site.post("/api/cases/1/close", data={"who": "هشام"})
    assert states(case(site)["steps"]) == ["done", "done", "done", "current"]
    assert record(site)[-1] == {"step": "closed", "at": "2026-12-23T10:09:00", "who": "هشام", "skipped": False}


def test_a_step_that_did_not_happen_is_shown_as_skipped_never_as_done(site):
    send(site, WITH_ROOM)
    site.clock.now += timedelta(minutes=7)
    site.post("/api/cases/1/close", data={"who": "هشام"})
    steps = case(site)["steps"]
    assert states(steps) == ["done", "done", "skipped", "current"]
    assert steps[2]["at"] is None


def test_the_record_says_skipped_and_gives_the_step_no_time_and_no_name(site):
    """The record is evidence: it must never show a step that did not happen."""
    send(site, WITH_ROOM)
    site.clock.now += timedelta(minutes=7)
    site.post("/api/cases/1/close", data={"who": "هشام"})
    assert record(site) == [
        {"step": "received", "at": "2026-12-23T10:00:00", "who": copy.STEP_BY_SENDER, "skipped": False},
        {"step": "assigned", "at": "2026-12-23T10:00:00", "who": copy.STEP_BY_RASD, "skipped": False},
        {"step": "in_progress", "at": None, "who": None, "skipped": True, "noted_at": "2026-12-23T10:07:00"},
        {"step": "closed", "at": "2026-12-23T10:07:00", "who": "هشام", "skipped": False},
    ]
    events = site.get("/api/cases/1/events").json()["events"]
    assert {"what": "skipped in_progress", "who": "هشام", "at": "2026-12-23T10:07:00"} in events


def test_a_case_closed_while_it_still_waited_for_the_supervisor_skipped_two_steps(site):
    waiting_report(site)
    site.post("/api/cases/1/close", data={"who": "هشام"})
    assert states(case(site)["steps"]) == ["done", "skipped", "skipped", "current"]
    assert [(entry["step"], entry["skipped"]) for entry in record(site)] == [
        ("received", False), ("assigned", True), ("in_progress", True), ("closed", False),
    ]  # fmt: skip


def test_a_case_that_went_through_every_step_has_nothing_skipped(site):
    send(site, WITH_ROOM)
    site.post("/api/cases/1/acknowledge", data={"who": "هشام"})
    site.post("/api/cases/1/close", data={"who": "هشام"})
    assert "skipped" not in states(case(site)["steps"]) and not any(entry["skipped"] for entry in record(site))
    assert not any(event["what"].startswith("skipped") for event in site.get("/api/cases/1/events").json()["events"])


def test_an_open_case_has_no_skipped_step_yet(site):
    send(site, WITH_ROOM)
    assert states(case(site)["steps"]) == ["done", "current", "todo", "todo"]


def test_the_board_and_the_sender_see_the_skipped_step_with_its_label(site):
    assert copy.STEP_STATES["skipped"] == "تُخطّيت"
    reply = send(site, WITH_ROOM)
    site.post("/api/cases/1/close", data={"who": "هشام"})
    page = site.get("/board").text
    assert "step-skipped" in page and "تُخطّيت" in page
    status = site.get(f"/api/reports/{reply['report_id']}/status").json()
    assert states(status["steps"]) == ["done", "done", "skipped", "current"]
    assert "step-skipped" in site.get("/static/style.css").text and "skipped" in site.get("/static/report.js").text


def test_every_open_assigned_case_can_be_acknowledged_from_the_board_not_only_critical_ones(site):
    send(site, WITH_ROOM)  # urgent
    assert 'data-action="acknowledge"' in site.get("/board").text
    site.post("/api/cases/1/acknowledge", data={"who": "هشام"})
    assert 'data-action="acknowledge"' not in site.get("/board").text


# --- the board ---------------------------------------------------------------------------------------------


def test_each_card_on_the_board_has_the_row_of_steps(site):
    send(site, WITH_ROOM)
    page = site.get("/board").text
    assert page.count('class="progress"') == 1
    for label in copy.STEPS.values():
        assert label in page
    assert page.count('aria-current="step"') == 1
    assert f'aria-label="{copy.STEPS_TITLE}"' in page


# --- status back to the sender -----------------------------------------------------------------------------


def test_the_reply_to_the_sender_carries_the_steps_of_the_case(site):
    reply = send(site, WITH_ROOM)
    assert states(reply["steps"]) == ["done", "current", "todo", "todo"]
    assert all(set(step) == {"key", "label", "state", "at"} for step in reply["steps"])  # no staff names go to the sender


def test_the_sender_can_ask_for_the_status_and_it_follows_the_case(site):
    reply = send(site, WITH_ROOM)
    site.clock.now += timedelta(minutes=4)
    site.post("/api/cases/1/acknowledge", data={"who": "هشام"})
    status = site.get(f"/api/reports/{reply['report_id']}/status").json()
    assert status["case_id"] == 1 and states(status["steps"]) == ["done", "done", "current", "todo"]
    assert status["steps"][2]["at"] == "2026-12-23T10:04:00"
    site.post("/api/cases/1/close", data={"who": "هشام"})
    assert states(site.get(f"/api/reports/{reply['report_id']}/status").json()["steps"])[-1] == "current"


def test_a_report_that_joined_another_case_shows_that_cases_steps(site):
    send(site, WITH_ROOM)
    site.post("/api/cases/1/acknowledge", data={"who": "هشام"})
    second = send(site, WITH_ROOM)
    assert second["merged"] is True
    assert states(second["steps"]) == ["done", "done", "current", "todo"]
    assert site.get(f"/api/reports/{second['report_id']}/status").json()["case_id"] == 1


def test_a_report_that_joins_a_case_after_its_answer_shows_that_cases_steps(site):
    send(site, WITH_ROOM)
    site.post("/api/cases/1/acknowledge", data={"who": "هشام"})
    reply = waiting_report(site)
    answered = site.post(f"/api/reports/{reply['report_id']}/answer", data={"reply": "907"}).json()
    assert answered["merged"] is True and states(answered["steps"]) == ["done", "done", "current", "todo"]
    db = sqlite3.connect(site.db)
    assert db.execute("select distinct case_id from steps").fetchall() == [(1,)]  # the removed card left no steps behind


def test_a_message_that_is_not_a_report_has_no_steps(site):
    site.engine.readings["صباح الخير"] = reading(type="not_a_report", **NO_PLACE)
    reply = send(site, "صباح الخير")
    assert reply["steps"] is None
    assert site.get(f"/api/reports/{reply['report_id']}/status").status_code == 404
    assert site.get("/api/reports/999/status").status_code == 404


def test_the_status_tells_the_sender_nothing_but_the_steps(site):
    site.engine.readings["نبيل سعد تعبان في غرفة 907"] = reading(type="health", pilgrim_name="نبيل سعد")
    reply = send(site, "نبيل سعد تعبان في غرفة 907")
    site.post("/api/cases/1/acknowledge", data={"who": "هشام"})
    answer = site.get(f"/api/reports/{reply['report_id']}/status")
    assert set(answer.json()) == {"case_id", "steps"}
    assert "نبيل" not in answer.text and "هشام" not in answer.text and "907" not in answer.text


def test_the_plain_form_page_shows_the_steps_too(site):
    page = site.post("/report", data={"text": WITH_ROOM, "hotel": HOTEL}).text
    assert 'class="progress"' in page and copy.STEPS["assigned"] in page


def test_the_phone_page_script_keeps_the_steps_fresh(site):
    script = site.get("/static/report.js").text
    assert "/status" in script and "setInterval" in script


# --- housekeeping ----------------------------------------------------------------------------------------------


def test_clearing_the_demo_clears_the_steps(site):
    send(site, WITH_ROOM)
    site.post("/api/operator/reset", data={"confirm": "yes"})
    assert sqlite3.connect(site.db).execute("select count(*) from steps").fetchone()[0] == 0


def test_the_steps_use_only_the_colours_of_the_design_brief(site):
    css = site.get("/static/style.css").text.upper()
    tokens = {"#EEF2F1", "#FFFFFF", "#10202B", "#4A5A66", "#D5DDDB", "#B3261E", "#B26A00", "#1F6F78", "#5B6770", "#0B6E4F"}
    assert set(re.findall(r"#[0-9A-F]{6}\b", css)) <= tokens
    assert ".PROGRESS" in css


# --- on stage the case goes through every step: acknowledge before closing ---------------------------------


def test_the_scenario_card_tells_the_supervisor_to_acknowledge_before_closing(site):
    page = site.get("/scenario-card").text
    assert f"«{copy.ACKNOWLEDGE}»" in page
    assert page.index(f"«{copy.ACKNOWLEDGE}»") < page.rindex(f"«{copy.CLOSE}»")


def test_the_operators_step_list_ends_with_acknowledge_then_close_on_the_board(site):
    page = site.get("/operator").text
    assert copy.STEP_ON_BOARD in page
    assert copy.ACKNOWLEDGE in copy.STEP_ON_BOARD and copy.CLOSE in copy.STEP_ON_BOARD
    assert copy.STEP_ON_BOARD.index(copy.ACKNOWLEDGE) < copy.STEP_ON_BOARD.index(copy.CLOSE)
    assert page.index(copy.STEP_CARD) < page.index(copy.STEP_ON_BOARD)
