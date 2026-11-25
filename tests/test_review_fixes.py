"""What the code review of the whole project found (stage 6). Each test is one finding.

No AI model and no network here. Everything is invented.
"""

import sqlite3
import threading
import time
from datetime import datetime, timedelta

import httpx
import pytest
import uvicorn
from fastapi.testclient import TestClient

from app import copy, main
from app.main import create_app
from rasd.askback import answer, ask_back
from rasd.cards import CardReading
from rasd.elm import SimulatedElm
from rasd.incidents import group_reports
from rasd.privacy import redact
from rasd.understand import Reading, build_report
from rasd.voice import FirstThatWorks, VoiceError

HOTEL = "برج السكينة"


def reading(**fields) -> Reading:
    base = dict(
        type="water", hotel="", location_kind="room", number_words="907", location_number="907", pilgrim_name="",
        risks=[], partial_words="", confidence="high",
    )  # fmt: skip
    base.update(fields)
    return Reading(**base)


LOST = dict(type="lost_pilgrim", location_kind="none", number_words="", location_number="")
NO_ROOM = dict(location_kind="room", number_words="", location_number="")
LOST_CARD = dict(type="nusuk_card", location_kind="none", number_words="", location_number="")


class Engine:
    def __init__(self, seconds=0.0):
        self.elm, self.readings, self.seconds, self.read_texts = SimulatedElm(), {}, seconds, []

    def read(self, text, photo_attached=False):
        self.read_texts.append(text)
        time.sleep(self.seconds)
        return build_report(text, self.readings.get(text, reading()), photo_attached=photo_attached)

    def transcribe(self, audio, filename):
        raise VoiceError("no voice here")

    def read_card(self, image, media_type):
        return CardReading(is_marked_as_specimen=True, full_name="ZAHID KARIM", visa_number="9990007788")


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
    return site.post("/api/reports", data={"text": text, "hotel": hotel})


def cases(site):
    return site.get("/api/board").json()["cases"]


# --- 1. a slow reading must not freeze the board or the replay switch ---------------------------------


def test_the_board_and_the_switch_answer_while_a_reading_is_slow(tmp_path):
    app = create_app(engine=Engine(seconds=1.5), db_path=tmp_path / "rasd.db")
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.02)
    base = f"http://127.0.0.1:{server.servers[0].sockets[0].getsockname()[1]}"
    try:
        slow = threading.Thread(target=lambda: httpx.post(f"{base}/api/reports", data={"text": "ما في موية", "hotel": HOTEL}, timeout=10))
        slow.start()
        time.sleep(0.3)  # the reading is under way
        started = time.perf_counter()
        assert httpx.get(f"{base}/api/board", timeout=10).status_code == 200
        assert httpx.post(f"{base}/api/operator/mode", data={"mode": "replay"}, timeout=10).json()["mode"] == "replay"
        assert time.perf_counter() - started < 0.8
        slow.join()
    finally:
        server.should_exit = True
        thread.join(timeout=5)


# --- 2. an engine that cannot start must not lose the report --------------------------------------------


def test_with_no_claude_key_a_report_is_still_saved_and_goes_to_the_supervisor(tmp_path, monkeypatch):
    monkeypatch.delenv("RASD_CLAUDE_KEY", raising=False)
    monkeypatch.setattr("rasd.understand.load_dotenv", lambda *a, **k: None)
    site = TestClient(create_app(db_path=tmp_path / "rasd.db"))
    reply = site.post("/api/reports", data={"text": "ما في موية في غرفة 907", "hotel": HOTEL})
    assert reply.status_code == 200 and copy.SENT_TO_SUPERVISOR in reply.json()["message"]
    assert site.get("/api/board").json()["cases"][0]["state"] == "waiting"
    assert site.post("/report", data={"text": "ما في موية في غرفة 907", "hotel": HOTEL}).status_code == 200


def test_the_operator_check_says_so_when_the_saved_scene_cannot_be_played(site, monkeypatch):
    def broken(*args, **kwargs):
        raise FileNotFoundError("a scene file is missing")

    monkeypatch.setattr("app.engine.ReplayEngine.__init__", broken)
    checks = {check["name"]: check for check in site.get("/api/operator/status").json()["checks"]}
    assert checks["saved_scene"]["ok"] is False


# --- 3. privacy ---------------------------------------------------------------------------------------------


def test_only_a_hotel_from_the_list_is_taken_from_the_sending_page(site):
    send(site, "ما في موية في غرفة 907", hotel="AHMAD SALEM passport A1234567")
    shown = site.get("/board").text + site.get("/api/board").text
    assert "AHMAD" not in shown and "A1234567" not in shown


def test_a_hotel_that_is_not_in_the_list_is_not_written_on_the_board(site):
    site.engine.readings["المكيف خربان في فندق سالم الدوسري غرفة 907"] = reading(type="ac", hotel="سالم الدوسري")
    send(site, "المكيف خربان في فندق سالم الدوسري غرفة 907", hotel="")
    shown = site.get("/board").text + site.get("/api/board").text
    assert "الدوسري" not in shown and copy.UNLISTED_HOTEL in shown


@pytest.mark.parametrize(
    "text, secret",
    [
        ("رقم جواز السفر 12345678", "12345678"),
        ("جواز سفر رقم 12345678", "12345678"),
        ("جوازه رقمه 12345678", "12345678"),
        ("رقم الجواز A 1234567", "1234567"),
        ("الجواز 1234 5678", "5678"),
        ("رقم التأشيرة 6012 345 678", "345"),
        ("visa 601-234-5678", "5678"),
        ("passport P12AB345", "P12AB345"),
        ("جوال ابنه 055 123 4567", "4567"),
        ("جواله +966 55 123 4567", "4567"),
    ],
)
def test_numbers_written_with_spaces_dashes_or_extra_words_are_hidden_too(text, secret):
    safe, private = redact(text)
    assert secret not in safe
    assert private.passport or private.visa or private.other


@pytest.mark.parametrize("text", ["جواز الحاج ضاع في غرفة 412", "المكيف خربان في غرفة 412 الدور 4", "الغرف 412 و 413 و 414 بدون موية", "باص 9 يتحرك 5 ونص"])
def test_rooms_and_small_numbers_are_not_hidden(text):
    assert redact(text)[0] == text


def asked(text, **fields):
    report = build_report(text, reading(**fields))
    return report, ask_back(report)


@pytest.mark.parametrize("reply", ["ما اعرف الغرفة، جوازه A1234567", "رقم جواله 0551234567", "بعد 5 دقايق اقول لك", "اسأل المشرف 2"])
def test_a_reply_that_is_not_a_room_does_not_become_one(reply):
    report, question = asked("المكيف خربان", type="ac", **NO_ROOM)
    completed = answer(report, question, reply)
    assert completed.loc_number is None and completed.needs_confirmation


@pytest.mark.parametrize("reply, number", [("305", "305"), ("غرفة 305", "305"), ("الغرفة رقم ٣٠٥", "305"), ("ثلاثمية وخمسة", "305")])
def test_a_real_room_reply_still_completes_the_report(reply, number):
    report, question = asked("المكيف خربان", type="ac", **NO_ROOM)
    assert answer(report, question, reply).loc_number == number


@pytest.mark.parametrize("reply", ["ما اعرف اسمه", "مدري", "لا أعرف", "بعدين اقول لك", "؟"])
def test_a_reply_that_is_not_a_name_does_not_become_one(reply):
    report, question = asked("حاج ضيّع بطاقة نسك في برج السكينة", hotel="برج السكينة", **LOST_CARD)
    assert question.field == "name"
    completed = answer(report, question, reply)
    assert completed.pilgrim_name is None and completed.needs_confirmation


def test_a_hotel_the_model_gives_that_is_not_in_the_message_sends_the_report_to_the_supervisor():
    report = build_report("المكيف خربان في غرفة 907", reading(type="ac", hotel="دار المنارة"))
    assert report.hotel is None and report.needs_confirmation and "hotel_not_confirmed" in report.reasons


# --- 4. the card step ----------------------------------------------------------------------------------------


def test_a_card_is_accepted_only_for_an_open_lost_pilgrim_case(site):
    send(site, "ما في موية في غرفة 907")
    refused = site.post("/api/cases/1/card", files={"photo": ("c.jpg", b"picture", "image/jpeg")})
    assert refused.status_code == 409 and refused.json()["message"] == copy.CARD_ONLY_FOR_LOST
    assert cases(site)[0]["identified"] is None and site.get("/api/board").json()["notifications"] == []
    site.engine.readings["حاج تايه"] = reading(**LOST)
    lost = send(site, "حاج تايه").json()
    site.post(f"/api/cases/{lost['case_id']}/close", data={"who": "سالم"})
    assert site.post(f"/api/cases/{lost['case_id']}/card", files={"photo": ("c.jpg", b"p", "image/jpeg")}).status_code == 409


def test_the_hidden_card_button_is_really_hidden_and_says_it_is_the_mock_card(site):
    assert "[hidden]" in site.get("/static/style.css").text
    assert "التجريبية" in copy.SHOW_CARD


# --- 7. the supervisor can read what was sent to them -------------------------------------------------------


def test_the_supervisor_page_shows_the_message_without_its_private_numbers(site):
    site.engine.readings["في مشكلة عند الحاج، جوازه [رقم جواز]"] = reading(type="unclear", confidence="low", **NO_ROOM)
    send(site, "في مشكلة عند الحاج، جوازه A1234567")
    page = site.get("/supervisor")
    assert page.status_code == 200 and '<html lang="ar" dir="rtl"' in page.text
    assert "في مشكلة عند الحاج" in page.text and "A1234567" not in page.text
    assert copy.FLAG_REASONS["low_confidence"] in page.text
    assert "في مشكلة عند الحاج" not in site.get("/board").text  # never on the big screen


def test_the_supervisor_page_lists_only_what_waits_for_the_supervisor(site):
    send(site, "ما في موية في غرفة 907")
    assert copy.NOTHING_WAITING in site.get("/supervisor").text


# --- 8. after the supervisor confirms a lost card, its clock starts ----------------------------------------------


def test_a_lost_card_report_confirmed_by_the_supervisor_gets_its_24_hour_clock(site):
    text = "نبيل سعد ضيّع بطاقة نسك في برج السكينة"
    site.engine.readings[text] = reading(hotel="برج السكينة", pilgrim_name="نبيل سعد", confidence="low", **LOST_CARD)
    send(site, text)
    assert cases(site)[0]["replacement_due"] is None
    site.clock.now += timedelta(minutes=10)
    site.post("/api/cases/1/confirm", data={"who": "سالم"})
    assert cases(site)[0]["replacement_due"] == "2026-12-24T10:00:00"  # 24 hours from the report, not from the confirmation


# --- 11. two different lost pilgrims at one counter -----------------------------------------------------------------


def lost(name="", room=""):
    kind = dict(location_kind="room", number_words=room, location_number=room) if room else dict(location_kind="none", number_words="", location_number="")
    text = f"حاج تايه {name} {room}".strip()
    return build_report(text + " في برج السكينة", reading(type="lost_pilgrim", hotel="برج السكينة", pilgrim_name=name, **kind))


def grouped(*reports):
    start = datetime(2026, 12, 23, 10, 0)
    return [incident.report_ids for incident in group_reports([(i, start + timedelta(minutes=5 * i), r) for i, r in enumerate(reports, 1)])]


def test_two_lost_pilgrims_with_different_names_are_two_cases():
    assert grouped(lost(name="يوسف"), lost(name="مريم")) == [[1], [2]]


def test_two_lost_pilgrims_with_different_rooms_are_two_cases():
    assert grouped(lost(room="305"), lost(room="410")) == [[1], [2]]


def test_a_report_with_no_name_still_joins_the_named_one_and_the_same_name_in_urdu_letters_joins():
    assert grouped(lost(), lost(name="زاهد كريم"), lost(name="زاہد کریم")) == [[1, 2, 3]]


# --- 12. the numbers people see agree -------------------------------------------------------------------------------


def test_the_board_label_carries_the_number_the_sender_was_told(site):
    site.engine.readings["صباح الخير"] = reading(type="not_a_report", **NO_ROOM)
    send(site, "صباح الخير")
    reply = send(site, "ما في موية في غرفة 907").json()
    assert "البلاغ 2" in reply["message"]
    assert cases(site)[0]["label"] == "بلاغ 2"


def test_a_message_that_is_not_a_report_is_not_kept(site):
    site.engine.readings["صباح الخير يا شباب"] = reading(type="not_a_report", **NO_ROOM)
    send(site, "صباح الخير يا شباب")
    stored = sqlite3.connect(site.db).execute("select safe_text from reports").fetchall()
    assert stored == [("",)]


# --- 13, 14 and smaller ones ------------------------------------------------------------------------------------------


def test_the_first_error_of_the_live_voice_service_is_the_one_reported():
    class Live:
        def transcribe(self, audio, filename):
            raise VoiceError("the service answered with error 401")

    class Saved:
        def transcribe(self, audio, filename):
            raise VoiceError("not a saved note")

    with pytest.raises(VoiceError, match="401"):
        FirstThatWorks(Live(), Saved()).transcribe(b"a", "a.wav")


def test_a_very_long_message_is_not_sent_to_the_model_and_goes_to_the_supervisor(site):
    reply = send(site, "كلام " * 2000)
    assert reply.status_code == 200 and copy.SENT_TO_SUPERVISOR in reply.json()["message"]
    assert site.engine.read_texts == []
    assert cases(site)[0]["state"] == "waiting"


def test_a_pilgrim_photo_that_is_too_large_is_refused(site, monkeypatch):
    monkeypatch.setattr(main, "MAX_PHOTO_BYTES", 10)
    reply = site.post("/api/reports", data={"text": "حاج تايه", "hotel": HOTEL}, files={"pilgrim_photo": ("p.jpg", b"x" * 11, "image/jpeg")})
    assert reply.status_code == 413 and reply.json()["message"] == copy.PHOTO_TOO_LARGE


def test_the_simulated_lookup_refuses_a_body_that_is_not_what_it_expects(site):
    assert site.post("/simulated-elm/lookup", json=["not", "an", "object"]).status_code == 400
    assert site.post("/simulated-elm/lookup", content=b"not json").status_code == 400


def test_acknowledging_twice_is_logged_once(site):
    site.engine.readings["حاج تايه"] = reading(**LOST)
    send(site, "حاج تايه")
    site.post("/api/cases/1/acknowledge", data={"who": "سالم"})
    site.post("/api/cases/1/acknowledge", data={"who": "هشام"})
    events = [e for e in site.get("/api/cases/1/events").json()["events"] if e["what"] == "acknowledged"]
    assert [e["who"] for e in events] == ["سالم"]


def test_the_sending_page_keeps_working_when_the_browser_has_scripts_but_no_fetch(site):
    script = site.get("/static/report.js").text
    assert "window.fetch" in script.split("addEventListener")[0]  # checked before any handler takes over the form
    assert "T.resend" in script
