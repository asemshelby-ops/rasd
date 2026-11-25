"""Demo safety: the replay switch, timing, old phones, limits, and the risks of a live demo.

Nothing here calls an AI model or the network. Everything is invented.
"""

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import copy, main
from app.engine import ReplayEngine
from app.main import create_app
from demo import scene
from rasd.cards import CardReading
from rasd.elm import SimulatedElm
from rasd.understand import Reading, build_report
from rasd.voice import VoiceError


def reading(**fields) -> Reading:
    base = dict(
        type="water", hotel="", location_kind="room", number_words="907", location_number="907", pilgrim_name="",
        risks=[], partial_words="", confidence="high",
    )  # fmt: skip
    base.update(fields)
    return Reading(**base)


LOST = dict(type="lost_pilgrim", location_kind="none", number_words="", location_number="")


class LiveStandIn:
    """Stands in for the live engine and counts how often it is used."""

    def __init__(self):
        self.elm = SimulatedElm()
        self.used = []
        self.readings = {}
        self.broken = None  # an exception every call raises, when set

    def _use(self, what):
        self.used.append(what)
        if self.broken:
            raise self.broken

    def read(self, text, photo_attached=False):
        self._use("read")
        return build_report(text, self.readings.get(text, reading()), photo_attached=photo_attached)

    def transcribe(self, audio, filename):
        self._use("transcribe")
        saved = {
            (scene.SCENE_DIR / scene.COUNTER_FILE).read_bytes(): scene.COUNTER_NOTE,
            (scene.SCENE_DIR / scene.PILGRIM_FILE).read_bytes(): scene.PILGRIM_NOTE,
            b"noise": "ششش خخخ",
        }
        if audio not in saved:
            raise VoiceError("not a saved voice note")
        return saved[audio]

    def read_card(self, image, media_type):
        self._use("read_card")
        return CardReading(is_marked_as_specimen=True, full_name=scene.CARD_NAME, visa_number=scene.CARD_VISA)


class Clock:
    def __init__(self):
        self.now = datetime(2026, 12, 23, 10, 0, 0)

    def __call__(self):
        return self.now


@pytest.fixture
def site(tmp_path):
    live, clock = LiveStandIn(), Clock()
    live.readings[scene.COUNTER_NOTE] = reading(**LOST)
    live.readings[scene.PILGRIM_NOTE] = reading(**LOST, pilgrim_name="زاہد کریم")
    client = TestClient(create_app(engine=live, db_path=tmp_path / "rasd.db", now=clock))
    client.live, client.clock, client.db = live, clock, tmp_path / "rasd.db"
    return client


def step(site, name):
    return site.post(f"/api/operator/scene/{name}")


def cases(site):
    return site.get("/api/board").json()["cases"]


# --- the saved scene answers without any network ---------------------------------------------------


def test_the_saved_scene_has_a_saved_reading_for_each_voice_note_and_for_the_card():
    saved = json.loads((scene.SCENE_DIR / "saved_readings.json").read_text(encoding="utf-8"))
    assert set(saved["readings"]) == {scene.COUNTER_NOTE, scene.PILGRIM_NOTE}
    assert saved["card"] == {"file": scene.CARD_FILE, "full_name": scene.CARD_NAME, "visa_number": scene.CARD_VISA}
    assert saved["recorded_on"] and saved["model"]  # when and from which model the readings were recorded


def test_the_replay_engine_reads_the_scene_from_saved_files_only():
    replay = ReplayEngine()
    for file, words in ((scene.COUNTER_FILE, scene.COUNTER_NOTE), (scene.PILGRIM_FILE, scene.PILGRIM_NOTE)):
        assert replay.transcribe((scene.SCENE_DIR / file).read_bytes(), file) == words
        report = replay.read(words)
        assert report.type == "lost_pilgrim" and report.urgency == "critical"
    card = replay.read_card((scene.SCENE_DIR / scene.CARD_FILE).read_bytes(), "image/png")
    assert (card.full_name, card.visa_number) == (scene.CARD_NAME, scene.CARD_VISA)


def test_the_replay_engine_refuses_a_card_that_is_not_the_saved_one():
    assert ReplayEngine().read_card(b"some other picture", "image/png") is None


def test_in_replay_a_message_that_was_not_saved_goes_to_the_live_reader():
    live = LiveStandIn()
    report = ReplayEngine(otherwise=lambda: live).read("ما في موية في غرفة 907")
    assert live.used == ["read"] and report.type == "water"


def test_in_replay_with_no_live_reader_an_unsaved_message_goes_to_the_supervisor():
    def no_key():
        raise RuntimeError("RASD_CLAUDE_KEY is not set")

    report = ReplayEngine(otherwise=no_key).read("ما في موية في غرفة 907")
    assert report.needs_confirmation and report.reasons == ("not_understood",)


# --- the replay switch --------------------------------------------------------------------------------


def test_the_site_starts_live_and_the_operator_page_says_so(site):
    assert site.get("/api/operator/status").json()["mode"] == "live"
    page = site.get("/operator")
    assert page.status_code == 200 and copy.MODE_LIVE in page.text
    assert '<html lang="ar" dir="rtl"' in page.text


def test_the_operator_switches_to_replay_and_everyone_can_see_it(site):
    assert site.post("/api/operator/mode", data={"mode": "replay"}).json()["mode"] == "replay"
    assert copy.MODE_REPLAY in site.get("/operator").text
    assert copy.REPLAY_MODE_ON in site.get("/board").text
    assert copy.REPLAY_MODE_ON in site.get("/board/fragment").text
    site.post("/api/operator/mode", data={"mode": "live"})
    assert copy.REPLAY_MODE_ON not in site.get("/board").text


def test_an_unknown_mode_is_refused(site):
    assert site.post("/api/operator/mode", data={"mode": "magic"}).status_code == 400
    assert site.get("/api/operator/status").json()["mode"] == "live"


def test_the_mode_survives_a_restart(site):
    site.post("/api/operator/mode", data={"mode": "replay"})
    again = TestClient(create_app(engine=LiveStandIn(), db_path=site.db))
    assert again.get("/api/operator/status").json()["mode"] == "replay"


def test_in_replay_the_whole_scene_runs_with_the_live_path_dead(site):
    site.live.broken = RuntimeError("no network")
    site.post("/api/operator/mode", data={"mode": "replay"})
    first = step(site, "counter").json()
    second = step(site, "pilgrim").json()
    assert second["merged"] is True and second["case_id"] == first["case_id"]
    found = step(site, "card").json()
    assert found["identified"] is True
    (case,) = cases(site)
    assert case["count_text"] == "بلاغان، حالة واحدة" and case["priority"] == "critical"
    assert case["identified"]["supervisor"] == SimulatedElm().lookup(scene.CARD_NAME, scene.CARD_VISA).supervisor
    assert site.live.used == []  # the live engine was never touched


def test_a_case_that_came_from_saved_files_says_so_on_the_board(site):
    site.post("/api/operator/mode", data={"mode": "replay"})
    step(site, "counter")
    (case,) = cases(site)
    assert case["from_saved"] is True
    assert copy.FROM_SAVED in site.get("/board").text


def test_a_live_report_does_not_carry_the_saved_label(site):
    site.post("/api/reports", data={"text": "ما في موية في غرفة 907", "hotel": scene.REPORTING_HOTEL})
    assert cases(site)[0]["from_saved"] is False
    assert copy.FROM_SAVED not in site.get("/board").text


def test_in_live_mode_the_saved_voice_notes_go_through_the_live_path(site):
    step(site, "counter")
    assert site.live.used == ["transcribe", "read"]


def test_the_card_step_needs_a_lost_pilgrim_case_first(site):
    reply = step(site, "card")
    assert reply.status_code == 409 and reply.json()["message"] == copy.NO_CASE_FOR_CARD


def test_an_unknown_step_is_not_found(site):
    assert step(site, "dance").status_code == 404


# --- clearing the board between two demos ---------------------------------------------------------------


def test_clearing_the_demo_needs_a_yes_and_then_empties_everything(site):
    site.post("/api/reports", data={"text": "جواز X0012345 ضاع", "hotel": scene.REPORTING_HOTEL})
    assert site.post("/api/operator/reset").status_code == 400
    assert len(cases(site)) == 1
    assert site.post("/api/operator/reset", data={"confirm": "yes"}).status_code == 200
    assert cases(site) == [] and site.get("/api/board").json()["notifications"] == []
    db = sqlite3.connect(site.db)
    for table in ("reports", "cases", "events", "private_numbers", "notifications"):
        assert db.execute(f"select count(*) from {table}").fetchone()[0] == 0


def test_clearing_the_demo_keeps_the_mode(site):
    site.post("/api/operator/mode", data={"mode": "replay"})
    site.post("/api/operator/reset", data={"confirm": "yes"})
    assert site.get("/api/operator/status").json()["mode"] == "replay"


# --- how long from the end of a voice note to the case ---------------------------------------------------


def test_a_voice_note_reply_says_how_long_each_part_took(site):
    audio = (scene.SCENE_DIR / scene.COUNTER_FILE).read_bytes()
    reply = site.post("/api/voice", data={"hotel": scene.REPORTING_HOTEL}, files={"audio": ("a.wav", audio)}).json()
    took = reply["seconds"]
    assert set(took) == {"heard", "read", "total"}
    assert took["total"] >= took["heard"] >= 0 and took["total"] >= took["read"] >= 0


def test_the_operator_sees_the_time_of_the_last_voice_note(site):
    assert site.get("/api/operator/status").json()["last_voice"] is None
    step(site, "counter")
    last = site.get("/api/operator/status").json()["last_voice"]
    assert set(last) == {"heard", "read", "total"}
    assert copy.LAST_VOICE_TOOK in site.get("/operator").text


def test_the_board_asks_for_news_every_second(site):
    assert main.BOARD_REFRESH_SECONDS == 1
    assert '"refreshMs": 1000' in site.get("/board").text


# --- an old phone browser ------------------------------------------------------------------------------


def test_the_report_form_works_with_no_script_at_all(site):
    page = site.post("/report", data={"text": "ما في موية في غرفة 907", "hotel": scene.REPORTING_HOTEL})
    assert page.status_code == 200 and '<html lang="ar" dir="rtl"' in page.text
    assert copy.TYPES["water"] in page.text and "البلاغ 1" in page.text
    assert len(cases(site)) == 1


def test_the_plain_form_says_what_to_do_when_it_is_sent_empty(site):
    page = site.post("/report", data={"text": "  ", "hotel": scene.REPORTING_HOTEL})
    assert copy.EMPTY_MESSAGE in page.text and cases(site) == []


def test_the_report_page_is_a_real_form_and_takes_a_sound_file_where_recording_is_blocked(site):
    page = site.get("/report").text
    assert 'method="post"' in page and 'action="/report"' in page
    assert 'accept="audio/*"' in page and copy.ATTACH_AUDIO in page


# --- limits ---------------------------------------------------------------------------------------------


def test_a_card_photo_that_is_too_large_is_refused_with_what_to_do(site, monkeypatch):
    step(site, "counter")
    monkeypatch.setattr(main, "MAX_PHOTO_BYTES", 10)
    reply = site.post("/api/cases/1/card", files={"photo": ("card.jpg", b"x" * 11, "image/jpeg")})
    assert reply.status_code == 413 and reply.json()["message"] == copy.PHOTO_TOO_LARGE
    assert "read_card" not in site.live.used


def test_a_voice_note_that_is_too_large_is_refused_with_what_to_do(site, monkeypatch):
    monkeypatch.setattr(main, "MAX_AUDIO_BYTES", 10)
    reply = site.post("/api/voice", data={"hotel": scene.REPORTING_HOTEL}, files={"audio": ("a.wav", b"x" * 11)})
    assert reply.status_code == 413 and reply.json()["message"] == copy.AUDIO_TOO_LARGE
    assert site.live.used == []


# --- the risks of a live demo ---------------------------------------------------------------------------


def test_two_reports_in_the_same_second_from_two_phones_become_one_case(tmp_path):
    live, clock = LiveStandIn(), Clock()
    live.readings["حاج تايه عند الاستقبال"] = reading(**LOST)
    app = create_app(engine=live, db_path=tmp_path / "rasd.db", now=clock)
    start, replies = threading.Barrier(2), []

    def phone():
        client = TestClient(app)
        start.wait()
        replies.append(client.post("/api/reports", data={"text": "حاج تايه عند الاستقبال", "hotel": scene.REPORTING_HOTEL}).json())

    threads = [threading.Thread(target=phone) for _ in range(2)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(reply["report_id"] for reply in replies) == [1, 2]
    assert sorted(reply["merged"] for reply in replies) == [False, True]
    (case,) = TestClient(app).get("/api/board").json()["cases"]
    assert case["count"] == 2


def test_twelve_phones_at_once_lose_no_report(tmp_path):
    live = LiveStandIn()
    for room in range(12):
        text = f"ما في موية في غرفة {600 + room}"
        live.readings[text] = reading(number_words=str(600 + room), location_number=str(600 + room))
    app = create_app(engine=live, db_path=tmp_path / "rasd.db", now=Clock())
    start = threading.Barrier(12)

    def phone(text):
        client = TestClient(app)
        start.wait()
        assert client.post("/api/reports", data={"text": text, "hotel": scene.REPORTING_HOTEL}).status_code == 200

    threads = [threading.Thread(target=phone, args=(text,)) for text in live.readings]
    [t.start() for t in threads]
    [t.join() for t in threads]
    board = TestClient(app).get("/api/board").json()["cases"]
    assert len(board) == 12 and len({case["place"] for case in board}) == 12


def test_the_board_is_still_there_after_the_laptop_program_restarts(site):
    site.post("/api/reports", data={"text": "ما في موية في غرفة 907", "hotel": scene.REPORTING_HOTEL})
    site.post("/api/cases/1/acknowledge", data={"who": "سالم"})
    again = TestClient(create_app(engine=LiveStandIn(), db_path=site.db, now=site.clock))
    (case,) = again.get("/api/board").json()["cases"]
    assert case["id"] == 1 and case["acknowledged"] is True


def test_when_the_reading_breaks_in_an_unexpected_way_the_report_still_reaches_the_supervisor(site):
    """A bad network, or a fault we did not think of: the page must answer and nothing is lost."""
    site.live.broken = TimeoutError("the hotspot dropped")
    reply = site.post("/api/reports", data={"text": "ما في موية في غرفة 907", "hotel": scene.REPORTING_HOTEL})
    assert reply.status_code == 200 and copy.SENT_TO_SUPERVISOR in reply.json()["message"]
    (case,) = cases(site)
    assert case["state"] == "waiting" and case["priority"] == "urgent"


def test_when_the_card_reader_breaks_the_sender_is_told_what_to_do(site):
    step(site, "counter")
    site.live.broken = TimeoutError("the hotspot dropped")
    reply = site.post("/api/cases/1/card", files={"photo": ("card.jpg", b"picture", "image/jpeg")})
    assert reply.status_code == 422 and reply.json()["message"] == copy.CARD_REFUSED


def test_a_voice_note_that_is_only_noise_goes_to_the_supervisor_with_one_question(site):
    site.live.readings["ششش خخخ"] = reading(type="unclear", location_kind="none", number_words="", location_number="", confidence="low")
    reply = site.post("/api/voice", data={"hotel": scene.REPORTING_HOTEL}, files={"audio": ("n.wav", b"noise")}).json()
    assert reply["question"]["text"] == "ما المشكلة؟" and reply["question"]["options"]
    assert cases(site)[0]["state"] == "waiting"


def test_a_double_tap_on_close_closes_once_and_says_so(site):
    site.post("/api/reports", data={"text": "ما في موية في غرفة 907", "hotel": scene.REPORTING_HOTEL})
    assert site.post("/api/cases/1/close", data={"who": "سالم"}).status_code == 200
    again = site.post("/api/cases/1/close", data={"who": "سالم"})
    assert again.status_code == 409 and again.json()["message"] == copy.ALREADY_CLOSED
    closes = [e for e in site.get("/api/cases/1/events").json()["events"] if e["what"] == "closed"]
    assert len(closes) == 1


# --- the printable scenario card ---------------------------------------------------------------------------


def test_the_scenario_card_has_the_exact_sentences_of_the_scene(site):
    page = site.get("/scenario-card")
    assert page.status_code == 200 and '<html lang="ar" dir="rtl"' in page.text
    assert scene.COUNTER_NOTE in page.text and scene.PILGRIM_NOTE in page.text
    assert copy.CARD_FOR_JUDGE in page.text and copy.CARD_FOR_OPERATOR in page.text
    assert copy.CARD_IF_LIVE_FAILS in page.text
    assert copy.SIMULATED in page.text  # the card tells the judge which parts are simulated


def test_the_operator_page_checks_what_the_demo_needs(site):
    status = site.get("/api/operator/status").json()
    assert {check["name"] for check in status["checks"]} >= {"claude_key", "speech_key", "saved_scene"}
    assert all(set(check) == {"name", "ok", "text"} for check in status["checks"])
