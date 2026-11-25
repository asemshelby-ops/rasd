"""The rules behind the demo scene. No web page and no AI model here.

Every person, company, hotel and number is invented.
"""

import json
from datetime import datetime, timedelta

import anthropic
import httpx2
import pytest

from rasd.cards import CardReading, read_mock_card
from rasd.cases import REPLACEMENT_HOURS, replacement_request, with_reporting_hotel
from rasd.elm import SimulatedElm
from rasd.incidents import LOST_PILGRIM_WINDOW_MINUTES, add_report, group_reports
from rasd.understand import Understanding
from rasd.voice import NoTranscriber, SavedTranscripts, VoiceError

START = datetime(2026, 12, 23, 10, 0)


def after(minutes: int) -> datetime:
    return START + timedelta(minutes=minutes)


def report(**changes) -> Understanding:
    """A lost pilgrim reported from the counter of برج السكينة, with no room."""
    fields = dict(
        type="lost_pilgrim", loc_kind="none", loc_number=None, urgency="critical", owner="pilgrim_affairs",
        deadline_minutes=30, confidence="high", needs_confirmation=False, reasons=(), hotel="برج السكينة",
    )  # fmt: skip
    fields.update(changes)
    return Understanding(**fields)


def grouped(*items) -> list[list[int]]:
    arrivals = [(i, after(minutes), r) for i, (minutes, r) in enumerate(items, start=1)]
    return [incident.report_ids for incident in group_reports(arrivals)]


# --- two reports about one lost pilgrim ---------------------------------------------


def test_two_lost_pilgrim_reports_from_the_same_hotel_within_15_minutes_are_one_case():
    assert LOST_PILGRIM_WINDOW_MINUTES == 15
    assert grouped((0, report()), (4, report(pilgrim_name="زاهد كريم"))) == [[1, 2]]


def test_exactly_15_minutes_still_merges_and_16_does_not():
    assert grouped((0, report()), (15, report())) == [[1, 2]]
    assert grouped((0, report()), (16, report())) == [[1], [2]]


def test_lost_pilgrims_at_two_hotels_are_two_cases():
    assert grouped((0, report()), (4, report(hotel="دار المنارة"))) == [[1], [2]]


def test_a_lost_pilgrim_report_with_no_hotel_at_all_does_not_merge():
    nowhere = report(hotel=None, needs_confirmation=True, reasons=("no_location",))
    assert grouped((0, nowhere), (4, nowhere)) == [[1], [2]]


def test_the_15_minute_rule_is_only_for_lost_pilgrims():
    card = report(type="nusuk_card")
    assert grouped((0, card), (4, card)) == [[1], [2]]


def test_a_lost_pilgrim_report_that_needs_the_supervisor_still_joins_the_case():
    unsure = report(needs_confirmation=True, reasons=("low_confidence",))
    assert grouped((0, report()), (4, unsure)) == [[1, 2]]


def test_a_closed_lost_pilgrim_case_takes_no_more_reports():
    incidents = group_reports([(1, after(0), report())])
    incidents[0].closed_at = after(3)
    add_report(incidents, 2, after(5), report())
    assert [i.report_ids for i in incidents] == [[1], [2]]


def test_a_report_the_model_could_not_read_never_joins_a_lost_pilgrim_case():
    unread = report(type="unclear", needs_confirmation=True, reasons=("not_understood",))
    assert grouped((0, report()), (4, unread)) == [[1], [2]]


# --- the hotel the report was sent from ------------------------------------------------


def test_a_report_that_names_no_hotel_gets_the_hotel_it_was_sent_from():
    silent = report(hotel=None, needs_confirmation=True, reasons=("no_location",))
    settled = with_reporting_hotel(silent, "برج السكينة")
    assert settled.hotel == "برج السكينة"
    assert settled.needs_confirmation is False
    assert settled.reasons == ()


def test_a_hotel_named_in_the_message_wins_over_the_hotel_it_was_sent_from():
    assert with_reporting_hotel(report(hotel="دار المنارة"), "برج السكينة").hotel == "دار المنارة"


def test_no_reporting_hotel_changes_nothing():
    silent = report(hotel=None, needs_confirmation=True, reasons=("no_location",))
    assert with_reporting_hotel(silent, None) == silent
    assert with_reporting_hotel(silent, "  ") == silent


def test_a_message_that_is_not_a_report_gets_no_hotel():
    chat = report(type="not_a_report", hotel=None, owner="nobody", urgency="normal")
    assert with_reporting_hotel(chat, "برج السكينة").hotel is None


def test_a_fault_still_needs_its_room_when_only_the_reporting_hotel_is_known():
    fault = report(type="water", owner="maintenance", urgency="urgent", hotel=None, needs_confirmation=True, reasons=("no_location",))
    settled = with_reporting_hotel(fault, "برج السكينة")
    assert settled.hotel == "برج السكينة"
    assert settled.reasons == ("no_location",)


# --- a lost Nusuk card starts a replacement request ---------------------------------------


def lost_card(**changes) -> Understanding:
    fields = dict(type="nusuk_card", urgency="urgent", pilgrim_name="زاهد كريم", has_passport_number=True)
    fields.update(changes)
    return report(**fields)


def test_a_complete_lost_card_report_prefills_a_replacement_request_due_in_24_hours():
    assert REPLACEMENT_HOURS == 24
    request = replacement_request(lost_card(), reported_at=after(0))
    assert request.due_at == after(0) + timedelta(hours=24)
    assert (request.pilgrim_name, request.hotel) == ("زاهد كريم", "برج السكينة")
    assert request.has_passport_number is True and request.has_visa_number is False


def test_the_replacement_request_lists_what_is_still_missing_from_the_checklist():
    request = replacement_request(lost_card(), reported_at=after(0))
    assert "رقم التأشيرة" in request.missing
    assert "رقم الجواز" not in request.missing
    assert "الاسم الكامل كما في الجواز" not in request.missing


def test_a_lost_card_report_that_still_needs_the_supervisor_starts_no_request():
    incomplete = lost_card(pilgrim_name=None, needs_confirmation=True, reasons=("no_pilgrim",))
    assert replacement_request(incomplete, reported_at=after(0)) is None


def test_other_types_start_no_replacement_request():
    assert replacement_request(report(), reported_at=after(0)) is None
    assert replacement_request(lost_card(type="no_nusuk_card"), reported_at=after(0)) is None


# --- the simulated Elm lookup -----------------------------------------------------------------


def test_the_elm_lookup_is_marked_as_simulated():
    assert SimulatedElm.SIMULATED is True


def test_the_lookup_finds_a_pilgrim_by_name_and_visa_number():
    elm = SimulatedElm()
    known = elm.records[0]
    found = elm.lookup(known["name"], known["visa_number"])
    assert (found.company, found.hotel, found.room, found.supervisor) == (
        known["company"], known["hotel"], known["room"], known["supervisor"],
    )  # fmt: skip


def test_the_lookup_accepts_the_name_in_another_case_and_with_extra_spaces():
    elm = SimulatedElm()
    known = elm.records[0]
    assert elm.lookup(f"  {known['name'].lower()} ", known["visa_number"]) is not None


def test_the_lookup_needs_both_the_name_and_the_visa_number_to_match():
    elm = SimulatedElm()
    known = elm.records[0]
    assert elm.lookup(known["name"], "0000000000") is None
    assert elm.lookup("SOMEONE ELSE", known["visa_number"]) is None
    assert elm.lookup("", "") is None


def test_printing_a_lookup_result_does_not_show_the_visa_number():
    elm = SimulatedElm()
    known = elm.records[0]
    assert known["visa_number"] not in repr(elm.lookup(known["name"], known["visa_number"]))


# --- voice: speech to text behind one interface ------------------------------------------------


def test_saved_transcripts_give_the_text_of_a_saved_voice_note(tmp_path):
    audio = b"RIFF....fake audio bytes"
    saved = SavedTranscripts({SavedTranscripts.key_of(audio): "في حاج تايه عند الاستقبال"})
    assert saved.transcribe(audio, "note.wav") == "في حاج تايه عند الاستقبال"


def test_a_voice_note_that_was_never_saved_is_an_error_with_a_reason():
    saved = SavedTranscripts({})
    with pytest.raises(VoiceError, match="saved"):
        saved.transcribe(b"other audio", "note.wav")


def test_with_no_transcriber_every_voice_note_is_an_error_that_says_what_to_set():
    with pytest.raises(VoiceError, match="RASD_OPENAI_KEY"):
        NoTranscriber().transcribe(b"audio", "note.wav")


# --- reading the mock Nusuk card with vision ----------------------------------------------------


def vision_client(answer: dict, sent: list) -> anthropic.Anthropic:
    def handler(request):
        sent.append(json.loads(request.content))
        return httpx2.Response(
            200,
            json={
                "id": "msg_test", "type": "message", "role": "assistant", "model": "claude-haiku-5-5",
                "content": [{"type": "text", "text": json.dumps(answer)}],
                "stop_reason": "end_turn", "stop_sequence": None,
                "usage": {"input_tokens": 700, "output_tokens": 40},
            },
        )  # fmt: skip

    return anthropic.Anthropic(
        api_key="test-key", max_retries=0, http_client=anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(handler))
    )


MOCK = {"is_marked_as_specimen": True, "full_name": "ZAHID KARIM", "visa_number": "9990004321"}


def test_the_card_photo_is_sent_to_the_model_as_an_image():
    sent = []
    read_mock_card(b"\x89PNG fake image", "image/png", vision_client(MOCK, sent))
    blocks = sent[0]["messages"][0]["content"]
    assert blocks[0]["type"] == "image"
    assert blocks[0]["source"]["media_type"] == "image/png"


def test_a_card_marked_as_a_specimen_gives_the_name_and_the_visa_number():
    reading = read_mock_card(b"image", "image/png", vision_client(MOCK, []))
    assert (reading.full_name, reading.visa_number) == ("ZAHID KARIM", "9990004321")


def test_a_card_that_is_not_marked_as_a_specimen_is_refused_and_nothing_is_read_from_it():
    real_looking = dict(MOCK, is_marked_as_specimen=False)
    assert read_mock_card(b"image", "image/png", vision_client(real_looking, [])) is None


def test_a_card_reading_never_prints_the_visa_number():
    reading = CardReading(**MOCK)
    assert "9990004321" not in repr(reading) and "9990004321" not in str(reading)


def test_a_failed_call_gives_no_reading_instead_of_a_crash():
    def handler(request):
        raise httpx2.ConnectError("no internet", request=request)

    client = anthropic.Anthropic(
        api_key="test-key", max_retries=0, http_client=anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(handler))
    )
    assert read_mock_card(b"image", "image/png", client) is None
