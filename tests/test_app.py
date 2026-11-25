"""The demo pages: reporting page, board, lost-card flow, Elm view, before-and-after page.

The engine is a stand-in, so nothing here calls an AI model or the network.
Every person, hotel, company and number is invented.
"""

import json
import sqlite3
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app import copy
from app.main import create_app
from rasd.cards import CardReading
from rasd.elm import SimulatedElm
from rasd.understand import Reading, build_report
from rasd.voice import VoiceError

HOTEL = "برج السكينة"
COUNTER_NOTE = "عندنا في الاستقبال حاج كبير في السن تايه ما يتكلم عربي"
PILGRIM_NOTE = "میرا نام محمد اشرف ہے، میں راستہ بھول گیا ہوں"
CARD_PHOTO = b"\x89PNG the mock card"
VISA = "9990004321"


def reading(**fields) -> Reading:
    base = dict(
        type="water", hotel="", location_kind="room", number_words="907", location_number="907", pilgrim_name="",
        risks=[], partial_words="", confidence="high",
    )  # fmt: skip
    base.update(fields)
    return Reading(**base)


LOST = dict(type="lost_pilgrim", location_kind="none", number_words="", location_number="")


class StandInEngine:
    """Answers like the real engine, from a table the test fills in."""

    def __init__(self):
        self.elm = SimulatedElm()
        self.readings = {
            COUNTER_NOTE: reading(**LOST, risks=[{"kind": "elderly", "words": "حاج كبير في السن"}]),
            PILGRIM_NOTE: reading(**LOST, pilgrim_name="محمد اشرف"),
        }
        self.voice = {b"counter audio": COUNTER_NOTE, b"pilgrim audio": PILGRIM_NOTE}
        self.cards = {CARD_PHOTO: CardReading(is_marked_as_specimen=True, full_name="MUHAMMAD ASHRAF", visa_number=VISA)}
        self.read_calls = []

    def read(self, text, photo_attached=False):
        self.read_calls.append(text)
        return build_report(text, self.readings.get(text, reading()), photo_attached=photo_attached)

    def transcribe(self, audio, filename):
        if audio not in self.voice:
            raise VoiceError("this voice note is not one of the saved ones")
        return self.voice[audio]

    def read_card(self, image, media_type):
        return self.cards.get(image)


class Clock:
    def __init__(self):
        self.now = datetime(2026, 12, 23, 10, 0, 0)

    def __call__(self):
        return self.now

    def forward(self, **amount):
        self.now += timedelta(**amount)


@pytest.fixture
def site(tmp_path):
    engine, clock = StandInEngine(), Clock()
    app = create_app(engine=engine, db_path=tmp_path / "rasd.db", now=clock)
    client = TestClient(app)
    client.engine, client.clock, client.db = engine, clock, tmp_path / "rasd.db"
    return client


def send(site, text, hotel=HOTEL, **files):
    return site.post("/api/reports", data={"text": text, "hotel": hotel}, files=files or None).json()


def board(site):
    return site.get("/api/board").json()["cases"]


def everything_public(site) -> str:
    """All the text of the pages that a hall can see."""
    return site.get("/board").text + site.get("/api/board").text + site.get("/elm").text + site.get("/api/elm").text


# --- sending a report --------------------------------------------------------------------


def test_a_sent_report_is_answered_with_its_number_and_where_it_went(site):
    reply = send(site, "ما في موية في غرفة 907")
    assert reply["report_id"] == 1 and reply["case_id"] == 1
    assert copy.TYPES["water"] in reply["message"]
    cases = board(site)
    assert len(cases) == 1
    assert cases[0]["type"] == copy.TYPES["water"]
    assert cases[0]["place"] == f"{HOTEL}، غرفة 907"
    assert cases[0]["priority"] == "urgent"


def test_the_report_gets_the_hotel_of_the_counter_it_was_sent_from(site):
    send(site, "ما في موية في غرفة 907", hotel="دار المنارة")
    assert board(site)[0]["place"] == "دار المنارة، غرفة 907"


def test_an_empty_message_is_refused_with_a_message_that_says_what_to_do(site):
    response = site.post("/api/reports", data={"text": "  ", "hotel": HOTEL})
    assert response.status_code == 400
    assert response.json()["message"] == copy.EMPTY_MESSAGE
    assert board(site) == []


def test_a_message_that_is_not_a_report_makes_no_case(site):
    site.engine.readings["صباح الخير"] = reading(type="not_a_report", location_kind="none", number_words="", location_number="")
    reply = send(site, "صباح الخير")
    assert reply["case_id"] is None
    assert reply["message"] == copy.NOT_A_REPORT
    assert board(site) == []


# --- the scene: two voice notes, one case ----------------------------------------------------


def voice(site, audio: bytes, hotel=HOTEL):
    return site.post("/api/voice", data={"hotel": hotel}, files={"audio": ("note.webm", audio, "audio/webm")})


def test_two_voice_notes_about_the_lost_pilgrim_become_one_case_with_two_reports(site):
    first = voice(site, b"counter audio").json()
    site.clock.forward(minutes=4)
    second = voice(site, b"pilgrim audio").json()
    assert first["case_id"] == second["case_id"]
    assert second["merged"] is True
    cases = board(site)
    assert len(cases) == 1
    assert cases[0]["count_text"] == "بلاغان، حالة واحدة"
    assert cases[0]["type"] == copy.TYPES["lost_pilgrim"]
    assert cases[0]["priority"] == "critical"
    assert "بلاغان، حالة واحدة" in site.get("/board").text


def test_the_voice_reply_shows_the_sender_what_was_heard(site):
    reply = voice(site, b"counter audio").json()
    assert reply["heard"] == COUNTER_NOTE


def test_a_lost_pilgrim_reported_again_after_16_minutes_is_a_new_case(site):
    voice(site, b"counter audio")
    site.clock.forward(minutes=16)
    voice(site, b"pilgrim audio")
    assert len(board(site)) == 2


def test_a_voice_note_that_cannot_be_written_down_is_an_error_the_sender_can_act_on(site):
    response = voice(site, b"unknown audio")
    assert response.status_code == 503
    assert response.json()["message"] == copy.VOICE_FAILED
    assert board(site) == []


# --- identification: the mock card, then the simulated Elm lookup --------------------------------


def lost_case(site) -> int:
    voice(site, b"counter audio")
    return voice(site, b"pilgrim audio").json()["case_id"]


def show_card(site, case_id, photo=CARD_PHOTO):
    return site.post(f"/api/cases/{case_id}/card", files={"photo": ("card.png", photo, "image/png")})


def test_the_mock_card_identifies_the_pilgrim_through_the_simulated_lookup(site):
    case_id = lost_case(site)
    reply = show_card(site, case_id).json()
    assert reply["identified"] is True
    case = board(site)[0]
    assert case["identified"] == {"company": "ضيوف الوادي", "hotel": "دار المنارة", "room": "731", "supervisor": "سالم"}
    assert copy.SIMULATED in case["identified_text"]


def test_his_companys_supervisor_gets_a_notification_marked_as_simulated(site):
    show_card(site, lost_case(site))
    notes = site.get("/api/board").json()["notifications"]
    assert len(notes) == 1
    assert "سالم" in notes[0]["text"] and "ضيوف الوادي" in notes[0]["text"]
    assert copy.SIMULATED in notes[0]["text"]


def test_a_card_that_is_not_the_marked_mock_card_is_refused(site):
    case_id = lost_case(site)
    response = show_card(site, case_id, photo=b"some other photo")
    assert response.status_code == 422
    assert response.json()["message"] == copy.CARD_REFUSED
    assert board(site)[0]["identified"] is None


def test_a_card_whose_holder_the_lookup_does_not_know_identifies_nobody(site):
    site.engine.cards[b"stranger"] = CardReading(is_marked_as_specimen=True, full_name="NO SUCH PERSON", visa_number="9990000000")
    response = show_card(site, lost_case(site), photo=b"stranger")
    assert response.status_code == 404
    assert response.json()["message"] == copy.NOT_IN_LOOKUP


def test_the_card_photo_itself_is_not_kept(site):
    show_card(site, lost_case(site))
    stored = b"".join(str(row).encode() for row in sqlite3.connect(site.db).iterdump())
    assert b"the mock card" not in stored
    assert not any(path.suffix in (".png", ".jpg", ".webm") for path in site.db.parent.iterdir())


# --- what the hall may never see ---------------------------------------------------------------------


def test_the_board_shows_only_the_first_letter_of_the_pilgrims_name(site):
    show_card(site, lost_case(site))
    public = everything_public(site)
    assert "م · بلاغ 1" in public or "M · بلاغ 1" in public
    for private in ("محمد اشرف", "MUHAMMAD", "ASHRAF", "Muhammad", "Ashraf"):
        assert private not in public


def test_the_board_never_shows_a_visa_or_passport_number(site):
    site.engine.readings["نبيل سعد ضيّع بطاقة نسك، جواز [رقم جواز]"] = reading(
        type="nusuk_card", location_kind="none", number_words="", location_number="", pilgrim_name="نبيل سعد"
    )
    send(site, "نبيل سعد ضيّع بطاقة نسك، جواز X0012345")
    show_card(site, lost_case(site))
    public = everything_public(site)
    assert "X0012345" not in public and VISA not in public
    assert "نبيل سعد" not in public


def test_the_engine_never_receives_a_passport_number(site):
    send(site, "نبيل سعد ضيّع بطاقة نسك، جواز X0012345")
    assert all("X0012345" not in text for text in site.engine.read_calls)


def test_the_real_numbers_are_kept_in_their_own_table_and_nowhere_else(site):
    send(site, "نبيل سعد ضيّع بطاقة نسك، جواز X0012345")
    database = sqlite3.connect(site.db)
    assert database.execute("select kind, value from private_numbers").fetchall() == [("passport", "X0012345")]
    elsewhere = [line for line in database.iterdump() if "X0012345" in line and "private_numbers" not in line]
    assert elsewhere == []


def test_the_board_never_shows_the_words_of_a_message(site):
    send(site, "ما في موية في غرفة 907 والحاج زعلان")
    assert "زعلان" not in everything_public(site)


def test_a_photo_of_the_pilgrim_is_only_recorded_as_attached(site):
    reply = send(site, "ما في موية في غرفة 907", pilgrim_photo=("p.jpg", b"JPEG the pilgrim's face", "image/jpeg"))
    assert reply["report_id"] == 1
    assert board(site)[0]["photo_attached"] is True
    stored = b"".join(str(row).encode() for row in sqlite3.connect(site.db).iterdump())
    assert b"the pilgrim's face" not in stored
    assert "<img" not in site.get("/board").text


# --- states, acknowledging and closing --------------------------------------------------------------


def test_cases_are_sorted_by_priority_with_critical_at_the_top(site):
    site.engine.readings["نظافة 355"] = reading(type="cleaning", number_words="355", location_number="355")
    send(site, "نظافة 355")
    send(site, "ما في موية في غرفة 907")
    lost_case(site)
    assert [case["priority"] for case in board(site)] == ["critical", "urgent", "normal"]


def test_a_report_that_needs_the_supervisor_waits_in_the_first_column(site):
    site.engine.readings["في مشكلة"] = reading(type="unclear", location_kind="none", number_words="", location_number="")
    send(site, "في مشكلة")
    assert board(site)[0]["state"] == "waiting"


def test_a_complete_report_goes_straight_to_its_owner(site):
    send(site, "ما في موية في غرفة 907")
    case = board(site)[0]
    assert case["state"] == "routed"
    assert case["owner"] == copy.OWNERS["maintenance"]


def test_a_critical_case_must_be_acknowledged_in_5_minutes_and_closed_in_30(site):
    lost_case(site)
    case = board(site)[0]
    assert case["acknowledge_due"] == "2026-12-23T10:05:00"
    assert case["close_due"] == "2026-12-23T10:30:00"
    assert copy.TRIAL_TIMES in site.get("/board").text


def test_a_case_past_its_time_is_shown_as_late(site):
    send(site, "ما في موية في غرفة 907")  # urgent: 15 trial minutes to close
    site.clock.forward(minutes=16)
    assert board(site)[0]["state"] == "late"


def test_acknowledging_records_who_and_when(site):
    case_id = lost_case(site)
    site.clock.forward(minutes=2)
    response = site.post(f"/api/cases/{case_id}/acknowledge", data={"who": "مشرف الوردية"})
    assert response.status_code == 200
    case = board(site)[0]
    assert case["acknowledged"] is True
    events = site.get(f"/api/cases/{case_id}/events").json()["events"]
    assert {"what": "acknowledged", "who": "مشرف الوردية", "at": "2026-12-23T10:02:00"} in events


def test_one_tap_closes_a_case_and_logs_the_time_and_who_closed_it(site):
    case_id = lost_case(site)
    site.clock.forward(minutes=9)
    response = site.post(f"/api/cases/{case_id}/close", data={"who": "مشرف الوردية"})
    assert response.status_code == 200
    case = board(site)[0]
    assert case["state"] == "closed"
    assert case["closed_by"] == "مشرف الوردية" and case["closed_at"] == "2026-12-23T10:09:00"
    events = site.get(f"/api/cases/{case_id}/events").json()["events"]
    assert {"what": "closed", "who": "مشرف الوردية", "at": "2026-12-23T10:09:00"} in events


def test_a_case_cannot_be_closed_without_saying_who_closes_it(site):
    case_id = lost_case(site)
    response = site.post(f"/api/cases/{case_id}/close", data={"who": "  "})
    assert response.status_code == 400
    assert response.json()["message"] == copy.NAME_NEEDED
    assert board(site)[0]["state"] != "closed"


def test_a_closed_case_cannot_be_closed_again(site):
    case_id = lost_case(site)
    site.post(f"/api/cases/{case_id}/close", data={"who": "مشرف الوردية"})
    again = site.post(f"/api/cases/{case_id}/close", data={"who": "موظف آخر"})
    assert again.status_code == 409
    assert board(site)[0]["closed_by"] == "مشرف الوردية"


def test_a_chat_message_saying_found_it_closes_nothing(site):
    lost_case(site)
    site.engine.readings["لقيناه 👍"] = reading(type="not_a_report", location_kind="none", number_words="", location_number="")
    send(site, "لقيناه 👍")
    assert board(site)[0]["state"] != "closed"
    assert len(board(site)) == 1


def test_a_new_report_about_a_closed_case_opens_a_new_case(site):
    send(site, "ما في موية في غرفة 907")
    site.post("/api/cases/1/close", data={"who": "مشرف الوردية"})
    site.clock.forward(minutes=5)
    assert send(site, "ما في موية في غرفة 907")["case_id"] == 2


def test_the_supervisor_can_confirm_a_waiting_case(site):
    site.engine.readings["المكيف خربان في 907"] = reading(type="ac", confidence="low")
    send(site, "المكيف خربان في 907")
    assert board(site)[0]["state"] == "waiting"
    site.post("/api/cases/1/confirm", data={"who": "مشرف الوردية"})
    assert board(site)[0]["state"] == "routed"


# --- ask-back on the reporting page -------------------------------------------------------------------


def test_a_report_that_lacks_its_room_gets_one_question_and_the_answer_completes_the_same_report(site):
    site.engine.readings["الموية مقطوعة"] = reading(location_kind="none", number_words="", location_number="")
    reply = send(site, "الموية مقطوعة")
    assert reply["question"]["text"] == "ما رقم الغرفة أو الدور؟"
    assert board(site)[0]["state"] == "waiting"

    answered = site.post(f"/api/reports/{reply['report_id']}/answer", data={"reply": "غرفة ٩٠٧"}).json()
    assert answered["report_id"] == reply["report_id"] and answered["case_id"] == reply["case_id"]
    assert answered["question"] is None
    cases = board(site)
    assert len(cases) == 1
    assert cases[0]["place"] == f"{HOTEL}، غرفة 907"
    assert cases[0]["state"] == "routed"


def test_a_question_offers_tap_answers_where_there_are_some(site):
    site.engine.readings["في مشكلة"] = reading(type="unclear", location_kind="none", number_words="", location_number="")
    reply = send(site, "في مشكلة")
    assert copy.TYPES["ac"] in reply["question"]["options"]


def test_a_report_is_not_asked_a_second_question(site):
    site.engine.readings["الموية مقطوعة"] = reading(location_kind="none", number_words="", location_number="")
    reply = send(site, "الموية مقطوعة")
    answered = site.post(f"/api/reports/{reply['report_id']}/answer", data={"reply": "ما أدري"}).json()
    assert answered["question"] is None
    again = site.post(f"/api/reports/{reply['report_id']}/answer", data={"reply": "907"})
    assert again.status_code == 409


# --- the lost-card flow and the Elm view ------------------------------------------------------------------


def lost_card(site):
    text = "نبيل سعد ضيّع بطاقة نسك"
    site.engine.readings[text] = reading(type="nusuk_card", location_kind="none", number_words="", location_number="", pilgrim_name="نبيل سعد")
    return send(site, text)


def test_a_complete_lost_card_report_starts_a_24_hour_clock_shown_on_the_case(site):
    lost_card(site)
    case = board(site)[0]
    assert case["replacement_due"] == "2026-12-24T10:00:00"
    assert copy.REPLACEMENT in site.get("/board").text


def test_the_replacement_request_is_prefilled_from_the_report(site):
    reply = lost_card(site)
    request = site.get(f"/api/cases/{reply['case_id']}/replacement").json()
    assert request["hotel"] == HOTEL
    assert request["pilgrim"] == "ن · بلاغ 1"
    assert "رقم التأشيرة" in request["missing"]


def test_the_prefilled_replacement_request_can_be_opened_from_the_case(site):
    site.engine.readings["نبيل سعد ضيّع بطاقة نسك، جواز [رقم جواز]"] = reading(
        type="nusuk_card", location_kind="none", number_words="", location_number="", pilgrim_name="نبيل سعد"
    )
    reply = send(site, "نبيل سعد ضيّع بطاقة نسك، جواز X0012345")
    page = site.get(f"/cases/{reply['case_id']}/replacement")
    assert page.status_code == 200
    assert HOTEL in page.text and "ن · بلاغ 1" in page.text
    assert copy.REQUEST_NOT_SENT in page.text  # nothing is sent to anyone: the page says so
    assert copy.NUMBER_KEPT in page.text  # the passport number is there, and is not shown
    assert "X0012345" not in page.text and "نبيل سعد" not in page.text
    assert f"/cases/{reply['case_id']}/replacement" in site.get("/board").text


def test_a_case_with_no_replacement_request_has_no_such_page(site):
    reply = send(site, "ما في موية في غرفة 907")
    assert site.get(f"/cases/{reply['case_id']}/replacement").status_code == 404


def test_a_lost_card_report_that_is_not_complete_starts_no_clock(site):
    site.engine.readings["حاج ضيّع بطاقة نسك"] = reading(type="nusuk_card", location_kind="none", number_words="", location_number="")
    send(site, "حاج ضيّع بطاقة نسك")
    assert board(site)[0]["replacement_due"] is None


def test_the_elm_view_lists_replacements_across_companies_under_a_simulated_data_banner(site):
    lost_card(site)
    page = site.get("/elm").text
    assert copy.SIMULATED_DATA_BANNER in page
    rows = site.get("/api/elm").json()["requests"]
    assert any(row["live"] for row in rows)
    assert len({row["company"] for row in rows}) >= 3
    assert all(row["simulated"] or row["live"] for row in rows)


def test_the_clusters_and_scorecard_are_one_static_screen_labelled_mockup(site):
    page = site.get("/elm/mockup").text
    assert copy.MOCKUP_LABEL in page
    assert copy.SAMPLE_NUMBERS in page


def test_the_simulated_elm_service_answers_a_lookup_and_says_it_is_simulated(site):
    found = site.post("/simulated-elm/lookup", json={"name": "MUHAMMAD ASHRAF", "visa_number": VISA}).json()
    assert found == {"simulated": True, "found": True, "company": "ضيوف الوادي", "hotel": "دار المنارة", "room": "731", "supervisor": "سالم"}
    missing = site.post("/simulated-elm/lookup", json={"name": "NOBODY", "visa_number": "1"}).json()
    assert missing == {"simulated": True, "found": False}


# --- the pages themselves ---------------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/", "/report?hotel=برج السكينة", "/board", "/elm", "/elm/mockup", "/before-after"])
def test_every_page_is_arabic_and_right_to_left(site, path):
    page = site.get(path)
    assert page.status_code == 200
    assert '<html lang="ar" dir="rtl"' in page.text  # the board adds a class after these


def test_the_reporting_page_carries_the_prototype_label_in_its_corner(site):
    assert copy.PROTOTYPE_LABEL in site.get(f"/report?hotel={HOTEL}").text


def test_the_before_and_after_page_puts_the_group_chat_next_to_the_same_reports_on_the_board(site):
    page = site.get("/before-after").text
    assert copy.BEFORE_TITLE in page and copy.AFTER_TITLE in page
    assert "لقيناها 👍" in page
    assert copy.FICTIONAL_GROUP in page


def test_the_board_page_names_its_band_and_its_three_columns(site):
    page = site.get("/board").text
    for title in copy.SECTIONS.values():  # the layout of the owner's design brief
        assert title in page


# --- the board for people who do not see it, or do not use a mouse (accessibility review) ---------------


def test_the_board_is_not_read_out_whole_every_time_it_refreshes(site):
    """The board re-draws itself every two seconds. Only what changed is announced, in a small status line."""
    send(site, "ما في موية في غرفة 907")
    page = site.get("/board").text
    assert '<div id="board">' in page  # no aria-live on the part that is re-drawn
    assert 'id="board-announcer"' in page and 'role="status"' in page
    assert 'data-case="1"' in page and 'data-state="routed"' in page  # what the script compares between refreshes


def test_the_operator_can_make_the_board_type_larger_for_the_hall(site):
    assert copy.LARGER in site.get("/operator").text  # the buttons moved off the board (design brief)
    assert '<html lang="ar" dir="rtl" class="board-root">' in site.get("/board").text


def test_the_number_beside_a_column_title_says_what_it_counts(site):
    assert copy.CASES_COUNT in site.get("/board").text
