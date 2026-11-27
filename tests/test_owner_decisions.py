"""The owner's decisions on the morning report (26 November 2026), and the speech-to-text path.

No AI model and no network here. Everything is invented.
"""

from datetime import datetime, timedelta

import httpx2
import pytest
from fastapi.testclient import TestClient

from app import copy
from app.main import create_app
from rasd.askback import answer, ask_back
from rasd.elm import SimulatedElm
from rasd.routing import HOTELS, near_hotel
from rasd.understand import Reading, build_report
from rasd.voice import OPENAI_MODEL, OpenAITranscriber, VoiceError

HOTEL = "برج السكينة"


def reading(**fields) -> Reading:
    base = dict(
        type="water", hotel="", location_kind="room", number_words="907", location_number="907", pilgrim_name="",
        risks=[], partial_words="", confidence="high",
    )  # fmt: skip
    base.update(fields)
    return Reading(**base)


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


def make_site(tmp_path, **options):
    engine, clock = Engine(), Clock()
    client = TestClient(create_app(engine=engine, db_path=tmp_path / "rasd.db", now=clock, **options))
    client.engine, client.clock = engine, clock
    return client


@pytest.fixture
def site(tmp_path):
    return make_site(tmp_path)


def send(site, text, hotel=HOTEL):
    return site.post("/api/reports", data={"text": text, "hotel": hotel}).json()


def cases(site):
    return site.get("/api/board").json()["cases"]


# --- 1. a late report that waits for the supervisor moves to the overdue column -----------------------


def unclear(site):
    site.engine.readings["في مشكلة"] = reading(type="unclear", location_kind="none", number_words="", location_number="", confidence="low")
    return send(site, "في مشكلة")


def test_a_waiting_report_past_its_time_is_in_the_overdue_column_and_still_says_it_waits(site):
    unclear(site)
    assert cases(site)[0]["state"] == "waiting"
    site.clock.now += timedelta(minutes=16)  # urgent: 15 minutes (trial value)
    (case,) = cases(site)
    assert case["state"] == "late" and case["waiting"] is True
    page = site.get("/board").text
    assert copy.STILL_WAITING in page and copy.CONFIRM in page  # the supervisor can still confirm it from there


def test_an_overdue_waiting_report_is_still_on_the_supervisor_page(site):
    unclear(site)
    site.clock.now += timedelta(minutes=16)
    assert "في مشكلة" in site.get("/supervisor").text


def test_confirming_an_overdue_report_keeps_it_overdue_but_no_longer_waiting(site):
    unclear(site)
    site.clock.now += timedelta(minutes=16)
    site.post("/api/cases/1/confirm", data={"who": "سالم"})
    (case,) = cases(site)
    assert case["state"] == "late" and case["waiting"] is False


# --- 2. a hotel name that is nearly right: never corrected silently, the sender is asked with one tap ----


@pytest.mark.parametrize("written, meant", [("برج السكينا", "برج السكينة"), ("نزل الياسمن", "نزل الياسمين"), ("دار المنار", "دار المنارة")])
def test_a_small_slip_is_near_one_hotel_of_the_list(written, meant):
    assert near_hotel(written) == meant


def test_a_name_far_from_every_hotel_or_already_in_the_list_is_near_nothing():
    assert near_hotel("قصر الغيم") is None
    assert near_hotel("برج") is None
    assert near_hotel(HOTELS[0]) is None


def slip():
    text = "المكيف خربان في برج السكينا غرفة 907"
    return build_report(text, reading(type="ac", hotel="برج السكينا"))


def test_a_nearly_right_hotel_is_not_corrected_and_the_report_waits():
    report = slip()
    assert report.hotel == "برج السكينا"  # as written: nothing is corrected silently
    assert report.needs_confirmation and "hotel_near_match" in report.reasons


def test_the_sender_is_asked_did_you_mean_with_two_taps():
    question = ask_back(slip())
    assert question.field == "hotel_confirm"
    assert question.text == "هل تقصد فندق برج السكينة؟"
    assert question.options == ("نعم", "لا")


def test_yes_sets_the_hotel_of_the_list_and_the_report_no_longer_waits():
    report = slip()
    completed = answer(report, ask_back(report), "نعم")
    assert completed.hotel == "برج السكينة" and not completed.needs_confirmation


def test_no_keeps_the_hotel_as_written_and_the_report_goes_on_without_a_guess():
    report = slip()
    completed = answer(report, ask_back(report), "لا")
    assert completed.hotel == "برج السكينا" and "hotel_near_match" not in completed.reasons
    assert ask_back(completed) is None


def test_any_other_reply_changes_nothing_and_the_supervisor_keeps_it():
    report = slip()
    completed = answer(report, ask_back(report), "مدري")
    assert completed.hotel == "برج السكينا" and completed.needs_confirmation


def test_through_the_pages_the_tap_completes_the_same_report(site):
    text = "المكيف خربان في برج السكينا غرفة 907"
    site.engine.readings[text] = reading(type="ac", hotel="برج السكينا")
    reply = send(site, text, hotel="")
    assert reply["question"] == {"text": "هل تقصد فندق برج السكينة؟", "options": ["نعم", "لا"]}
    assert cases(site)[0]["state"] == "waiting" and "السكينا" not in site.get("/board").text
    site.post(f"/api/reports/{reply['report_id']}/answer", data={"reply": "نعم"})
    (case,) = cases(site)
    assert case["state"] == "routed" and "برج السكينة" in case["place"]


# --- 3. a PIN on the operator page and the supervisor page ------------------------------------------------


PROTECTED_PAGES = ["/operator", "/supervisor"]


@pytest.fixture
def locked(tmp_path, monkeypatch):
    monkeypatch.setenv("RASD_PIN", "4821")
    return make_site(tmp_path)


@pytest.mark.parametrize("path", PROTECTED_PAGES)
def test_without_the_pin_the_page_asks_for_it(locked, path):
    page = locked.get(path, follow_redirects=True)
    assert copy.PIN_TITLE in page.text and copy.OPERATOR_TITLE not in page.text.replace(copy.PIN_TITLE, "")
    assert '<html lang="ar" dir="rtl"' in page.text


def test_without_the_pin_the_operator_actions_are_refused(locked):
    for path, data in [("/api/operator/mode", {"mode": "replay"}), ("/api/operator/reset", {"confirm": "yes"}), ("/operator/mode", {"mode": "replay"}), ("/api/operator/scene/counter", {})]:
        reply = locked.post(path, data=data, follow_redirects=False)
        assert reply.status_code in (401, 303), path
    assert locked.get("/api/operator/status").status_code == 401
    locked.post("/pin", data={"pin": "4821"})
    assert locked.get("/api/operator/status").json()["mode"] == "live"


def test_the_right_pin_opens_both_pages_and_a_wrong_one_does_not(locked):
    wrong = locked.post("/pin", data={"pin": "0000", "next": "/operator"})
    assert copy.PIN_WRONG in wrong.text
    assert copy.PIN_TITLE in locked.get("/operator", follow_redirects=True).text
    right = locked.post("/pin", data={"pin": "4821", "next": "/operator"}, follow_redirects=True)
    assert copy.MODE_LIVE in right.text
    assert locked.get("/supervisor").status_code == 200


def test_the_pin_accepts_arabic_digits(locked):
    locked.post("/pin", data={"pin": "٤٨٢١"})
    assert locked.get("/operator").status_code == 200


def test_the_board_and_the_sending_page_need_no_pin(locked):
    assert locked.get("/board").status_code == 200 and locked.get("/report").status_code == 200
    assert locked.post("/api/reports", data={"text": "ما في موية في غرفة 907", "hotel": HOTEL}).status_code == 200


def test_after_five_wrong_pins_the_door_stays_shut_for_a_while(locked):
    for _ in range(5):
        locked.post("/pin", data={"pin": "0000"})
    shut = locked.post("/pin", data={"pin": "4821"})
    assert copy.PIN_LOCKED in shut.text
    locked.clock.now += timedelta(seconds=61)
    locked.post("/pin", data={"pin": "4821"})
    assert locked.get("/operator").status_code == 200


def test_the_pin_never_goes_only_after_the_page_is_open_elsewhere(locked, tmp_path):
    locked.post("/pin", data={"pin": "4821"})
    stranger = TestClient(locked.app)
    assert copy.PIN_TITLE in stranger.get("/operator", follow_redirects=True).text


def test_with_no_pin_set_a_random_one_is_made_and_the_pages_stay_locked(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("RASD_PIN", raising=False)
    monkeypatch.setattr("app.main.dotenv_values", lambda *a, **k: {})
    site = make_site(tmp_path)
    assert copy.PIN_TITLE in site.get("/operator", follow_redirects=True).text
    pin = site.app.state.pin
    assert len(pin) == 4 and pin.isdigit()
    assert pin in capsys.readouterr().out  # printed once in the terminal of the laptop, for the team


# --- speech to text: ready for the key ------------------------------------------------------------------------


def transcriber(handler):
    return OpenAITranscriber("test-key", client=httpx2.Client(transport=httpx2.MockTransport(handler)))


def test_the_request_to_the_speech_service_is_what_the_service_expects():
    seen = {}

    def handler(request):
        seen["url"], seen["auth"], seen["body"] = str(request.url), request.headers["authorization"], request.read()
        return httpx2.Response(200, json={"text": " المكيف خربان في غرفة 907 "})

    assert transcriber(handler).transcribe(b"sound bytes", "note.m4a") == "المكيف خربان في غرفة 907"
    assert seen["url"] == "https://api.openai.com/v1/audio/transcriptions"
    assert seen["auth"] == "Bearer test-key"
    assert OPENAI_MODEL.encode() in seen["body"] and b'filename="note.m4a"' in seen["body"] and b"sound bytes" in seen["body"]


@pytest.mark.parametrize("status, hint", [(401, "key"), (429, "credit"), (400, "recording"), (500, "500")])
def test_an_error_of_the_speech_service_says_what_to_check(status, hint):
    with pytest.raises(VoiceError, match=hint):
        transcriber(lambda request: httpx2.Response(status, json={"error": {"message": "no"}})).transcribe(b"a", "a.m4a")


def test_a_dropped_network_is_a_voice_error_not_a_crash():
    def handler(request):
        raise httpx2.ConnectError("no route")

    with pytest.raises(VoiceError, match="reach"):
        transcriber(handler).transcribe(b"a", "a.m4a")


def test_an_error_never_carries_the_key():
    with pytest.raises(VoiceError) as error:
        transcriber(lambda request: httpx2.Response(401, json={})).transcribe(b"a", "a.m4a")
    assert "test-key" not in str(error.value)


def test_the_check_tool_prints_the_words_the_time_and_what_rasd_makes_of_them(tmp_path, capsys):
    from demo.check_speech import check

    recording = tmp_path / "note.m4a"
    recording.write_bytes(b"sound")

    class Hears:
        def transcribe(self, audio, filename):
            return "المكيف خربان في غرفة 907"

    assert check(recording, Hears(), read=None) == 0
    printed = capsys.readouterr().out
    assert "Words heard" in printed and "Seconds" in printed


def test_the_check_tool_says_what_to_do_when_the_key_is_missing(tmp_path, capsys, monkeypatch):
    from demo import check_speech

    monkeypatch.delenv("RASD_OPENAI_KEY", raising=False)
    monkeypatch.setattr(check_speech, "load_dotenv", lambda *a, **k: None)
    recording = tmp_path / "note.m4a"
    recording.write_bytes(b"sound")
    assert check_speech.main([str(recording)]) != 0
    assert "RASD_OPENAI_KEY" in capsys.readouterr().err


# --- after "نعم", the duplicate check runs again against the open cases of that hotel ---------------------

FIRST = "المكيف خربان في برج السكينة غرفة 907"
SLIP = "المكيف خربان في برج السكينا غرفة 907"


def first_then_slip(site, minutes_between=5):
    site.engine.readings[FIRST] = reading(type="ac", hotel="برج السكينة")
    site.engine.readings[SLIP] = reading(type="ac", hotel="برج السكينا")
    send(site, FIRST, hotel="")
    site.clock.now += timedelta(minutes=minutes_between)
    return send(site, SLIP, hotel="")


def tap(site, reply, answer_text):
    return site.post(f"/api/reports/{reply['report_id']}/answer", data={"reply": answer_text}).json()


def test_before_the_tap_the_slip_is_its_own_waiting_case(site):
    first_then_slip(site)
    assert [case["count"] for case in cases(site)] == [1, 1]


def test_yes_joins_the_report_to_the_open_case_of_that_hotel(site):
    reply = first_then_slip(site)
    answered = tap(site, reply, "نعم")
    assert answered["merged"] is True and answered["case_id"] == 1
    assert answered["message"] == copy.merged(1, 2)
    (case,) = cases(site)  # the slip's own card is gone
    assert case["id"] == 1 and case["count_text"] == "بلاغان، حالة واحدة" and case["state"] == "routed"
    whats = [event["what"] for event in site.get("/api/cases/1/events").json()["events"]]
    assert whats.count("reported") == 2 and "answered" in whats


def test_no_leaves_two_cases(site):
    tap(site, first_then_slip(site), "لا")
    assert len(cases(site)) == 2


def test_yes_does_not_join_a_closed_case(site):
    site.engine.readings[FIRST] = reading(type="ac", hotel="برج السكينة")
    site.engine.readings[SLIP] = reading(type="ac", hotel="برج السكينا")
    send(site, FIRST, hotel="")
    site.post("/api/cases/1/close", data={"who": "سالم"})
    answered = tap(site, send(site, SLIP, hotel=""), "نعم")
    assert answered["merged"] is False and len(cases(site)) == 2


def test_yes_does_not_join_a_case_older_than_the_merge_window(site):
    answered = tap(site, first_then_slip(site, minutes_between=61), "نعم")
    assert answered["merged"] is False and len(cases(site)) == 2


def test_the_window_is_counted_from_when_the_report_was_sent_not_from_the_tap(site):
    reply = first_then_slip(site, minutes_between=50)
    site.clock.now += timedelta(minutes=30)  # the sender taps half an hour later
    assert tap(site, reply, "نعم")["merged"] is True


def test_yes_does_not_join_a_case_about_another_room(site):
    site.engine.readings["المكيف خربان في برج السكينة غرفة 512"] = reading(type="ac", hotel="برج السكينة", number_words="512", location_number="512")
    site.engine.readings[SLIP] = reading(type="ac", hotel="برج السكينا")
    send(site, "المكيف خربان في برج السكينة غرفة 512", hotel="")
    assert tap(site, send(site, SLIP, hotel=""), "نعم")["merged"] is False


def test_what_belonged_to_the_report_moves_with_it(site, tmp_path):
    import sqlite3

    slip_with_number = SLIP + "، جواز الحاج A1234567"
    site.engine.readings[FIRST] = reading(type="ac", hotel="برج السكينة")
    site.engine.readings[SLIP + "، جواز الحاج [رقم جواز]"] = reading(type="ac", hotel="برج السكينا")
    send(site, FIRST, hotel="")
    tap(site, send(site, slip_with_number, hotel=""), "نعم")
    db = sqlite3.connect(tmp_path / "rasd.db")
    assert db.execute("select case_id from private_numbers").fetchall() == [(1,)]
    assert db.execute("select count(*) from cases").fetchone()[0] == 1
    assert db.execute("select distinct case_id from reports").fetchall() == [(1,)]


# --- the duplicate check also runs again after the sender gives the room or the floor ----------------------

WITH_ROOM = "ما في موية في غرفة 907"
NO_ROOM_TEXT = "الموية مقطوعة عندنا"
NO_PLACE = dict(location_kind="room", number_words="", location_number="")


def room_case_then_report_without_room(site, minutes_between=5):
    site.engine.readings[NO_ROOM_TEXT] = reading(**NO_PLACE)
    send(site, WITH_ROOM)
    site.clock.now += timedelta(minutes=minutes_between)
    reply = send(site, NO_ROOM_TEXT)
    assert reply["question"]["text"] == "ما رقم الغرفة أو الدور؟" and len(cases(site)) == 2
    return reply


def test_a_room_in_the_reply_joins_the_report_to_the_open_case_of_that_room(site):
    answered = tap(site, room_case_then_report_without_room(site), "907")
    assert answered["merged"] is True and answered["case_id"] == 1 and answered["message"] == copy.merged(1, 2)
    (case,) = cases(site)
    assert case["count_text"] == "بلاغان، حالة واحدة" and case["state"] == "routed"


def test_a_floor_in_the_reply_joins_the_open_case_of_that_floor(site):
    site.engine.readings["الكهرباء طافية في الدور 3"] = reading(type="power_elevator", location_kind="floor", number_words="3", location_number="3")
    site.engine.readings["الكهرباء طافية"] = reading(type="power_elevator", location_kind="none", number_words="", location_number="")
    send(site, "الكهرباء طافية في الدور 3")
    answered = tap(site, send(site, "الكهرباء طافية"), "الدور 3")
    assert answered["merged"] is True and len(cases(site)) == 1


def test_another_room_in_the_reply_stays_its_own_case(site):
    answered = tap(site, room_case_then_report_without_room(site), "512")
    assert answered["merged"] is False and len(cases(site)) == 2
    assert "512" in answered["message"]


def test_a_reply_with_no_room_changes_nothing(site):
    answered = tap(site, room_case_then_report_without_room(site), "مدري")
    assert answered["merged"] is False and len(cases(site)) == 2


def test_the_room_reply_keeps_the_60_minute_window_from_when_the_report_was_sent(site):
    reply = room_case_then_report_without_room(site, minutes_between=50)
    site.clock.now += timedelta(minutes=30)  # the tap comes 80 minutes after the first report
    assert tap(site, reply, "907")["merged"] is True


def test_the_room_reply_does_not_join_a_case_older_than_the_window_or_a_closed_one(site):
    assert tap(site, room_case_then_report_without_room(site, minutes_between=61), "907")["merged"] is False
    site.post("/api/operator/reset", data={"confirm": "yes"})
    reply = room_case_then_report_without_room(site)
    first_case = min(case["id"] for case in cases(site))
    site.post(f"/api/cases/{first_case}/close", data={"who": "سالم"})
    assert tap(site, reply, "907")["merged"] is False


def test_a_reply_with_only_a_name_does_not_run_the_check_again(site, monkeypatch):
    from app.store import Store

    calls = []
    real = Store._join_open_case
    monkeypatch.setattr(Store, "_join_open_case", lambda self, *args: calls.append(args) or real(self, *args))
    text = "حاج ضيّع بطاقة نسك في برج السكينة"
    site.engine.readings[text] = reading(type="nusuk_card", hotel="برج السكينة", location_kind="none", number_words="", location_number="")
    reply = send(site, text)
    assert reply["question"]["text"] == "ما اسم الحاج؟"
    tap(site, reply, "نبيل سعد")
    assert calls == []
    site.post("/api/operator/reset", data={"confirm": "yes"})
    tap(site, room_case_then_report_without_room(site), "907")
    assert len(calls) == 1  # the room reply does run it


# --- any answer that fills in the hotel, the room, the floor or the type runs the check again ----------------

LOST_HERE = "حاج تايه عند الاستقبال"
LOST_NOWHERE = "في حاج تايه ما يعرف وين يروح"
LOST_READING = dict(type="lost_pilgrim", location_kind="none", number_words="", location_number="")
UNCLEAR_907 = "في مشكلة في غرفة 907"


def lost_case_then_lost_report_without_hotel(site, minutes_between=5):
    site.engine.readings[LOST_HERE] = reading(**LOST_READING)
    site.engine.readings[LOST_NOWHERE] = reading(**LOST_READING)
    send(site, LOST_HERE)  # from the counter of برج السكينة
    site.clock.now += timedelta(minutes=minutes_between)
    reply = send(site, LOST_NOWHERE, hotel="")  # from no counter: no hotel
    assert reply["question"]["text"] == "في أي فندق؟" and HOTEL in reply["question"]["options"]
    return reply


def test_picking_the_hotel_from_the_buttons_joins_the_open_case_of_that_hotel(site):
    answered = tap(site, lost_case_then_lost_report_without_hotel(site), HOTEL)
    assert answered["merged"] is True and answered["case_id"] == 1
    (case,) = cases(site)
    assert case["count_text"] == "بلاغان، حالة واحدة"


def test_picking_another_hotel_stays_its_own_case(site):
    answered = tap(site, lost_case_then_lost_report_without_hotel(site), "دار المنارة")
    assert answered["merged"] is False and len(cases(site)) == 2


def test_the_hotel_pick_keeps_the_window_from_when_the_report_was_sent(site):
    reply = lost_case_then_lost_report_without_hotel(site, minutes_between=10)
    site.clock.now += timedelta(minutes=30)  # lost pilgrims merge within 15 minutes; the tap comes later
    assert tap(site, reply, HOTEL)["merged"] is True
    site.post("/api/operator/reset", data={"confirm": "yes"})
    assert tap(site, lost_case_then_lost_report_without_hotel(site, minutes_between=16), HOTEL)["merged"] is False


def water_case_then_unclear_report_in_the_same_room(site, minutes_between=5):
    site.engine.readings[UNCLEAR_907] = reading(type="unclear")
    send(site, WITH_ROOM)
    site.clock.now += timedelta(minutes=minutes_between)
    reply = send(site, UNCLEAR_907)
    assert reply["question"]["text"] == "ما المشكلة؟" and len(cases(site)) == 2
    return reply


def test_picking_the_type_joins_the_open_case_of_that_type_in_that_room(site):
    answered = tap(site, water_case_then_unclear_report_in_the_same_room(site), copy.TYPES["water"])
    assert answered["merged"] is True and answered["case_id"] == 1 and len(cases(site)) == 1


def test_picking_another_type_stays_its_own_case(site):
    answered = tap(site, water_case_then_unclear_report_in_the_same_room(site), copy.TYPES["ac"])
    assert answered["merged"] is False and len(cases(site)) == 2


def test_the_type_pick_keeps_the_60_minute_window_from_when_the_report_was_sent(site):
    reply = water_case_then_unclear_report_in_the_same_room(site, minutes_between=50)
    site.clock.now += timedelta(minutes=30)
    assert tap(site, reply, copy.TYPES["water"])["merged"] is True
    site.post("/api/operator/reset", data={"confirm": "yes"})
    late = water_case_then_unclear_report_in_the_same_room(site, minutes_between=61)
    assert tap(site, late, copy.TYPES["water"])["merged"] is False
