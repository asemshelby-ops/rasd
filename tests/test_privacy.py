"""Passport and visa numbers are taken out by plain code before any text goes to the model.

Every number here is fake.
"""

import json

import anthropic
import httpx2
import pytest

from rasd.privacy import PrivateNumbers, redact
from rasd.understand import understand

PASSPORT = "X0012345"
VISA = "9990001234"


# --- redact --------------------------------------------------------------------


def test_a_passport_number_after_its_label_is_replaced_by_a_placeholder():
    safe, private = redact(f"ضيع بطاقة نسك، جواز {PASSPORT} فندق برج الندى")
    assert PASSPORT not in safe
    assert "[رقم جواز]" in safe
    assert private.passport == (PASSPORT,)


def test_a_visa_number_after_its_label_is_replaced_by_a_placeholder():
    safe, private = redact(f"رقم التأشيرة: {VISA}")
    assert VISA not in safe
    assert "[رقم تأشيرة]" in safe
    assert private.visa == (VISA,)


@pytest.mark.parametrize("label", ["جواز", "الجواز", "جوازه", "باسبور", "passport", "Passport No", "پاسپورٹ نمبر"])
def test_passport_labels_in_arabic_english_and_urdu(label):
    safe, private = redact(f"{label} {PASSPORT}")
    assert PASSPORT not in safe and private.passport == (PASSPORT,)


@pytest.mark.parametrize("label", ["تأشيرة", "التاشيرة", "فيزا", "visa", "Visa number", "ویزا نمبر"])
def test_visa_labels_in_arabic_english_and_urdu(label):
    safe, private = redact(f"{label} {VISA}")
    assert VISA not in safe and private.visa == (VISA,)


def test_numbers_written_in_arabic_digits_are_found_too():
    safe, private = redact("رقم التأشيرة ٩٩٩٠٠٠١٢٣٤ ورقم الجواز X٠٠١٢٣٤٥")
    assert private.visa == (VISA,)
    assert private.passport == (PASSPORT,)
    assert "٩٩٩٠٠٠١٢٣٤" not in safe and "٠٠١٢٣٤٥" not in safe


def test_a_passport_shaped_number_without_a_label_is_taken_out():
    safe, private = redact(f"الحاج في فندق برج الندى {PASSPORT} ضيع البطاقة")
    assert PASSPORT not in safe
    assert private.passport == (PASSPORT,)


def test_a_long_number_without_a_label_is_taken_out_as_an_unknown_number():
    safe, private = redact("جوال الحاج 0500000123 وغرفته 907")
    assert "0500000123" not in safe
    assert "[رقم محجوب]" in safe
    assert private.other == ("0500000123",)


def test_room_and_floor_numbers_stay_in_the_text():
    safe, private = redact("غرفة 907 الدور 9 فندق برج الندى، وغرفة 1210")
    assert safe == "غرفة 907 الدور 9 فندق برج الندى، وغرفة 1210"
    assert private == PrivateNumbers()


def test_both_numbers_in_one_message_are_each_stored_under_their_kind():
    safe, private = redact(f"- جواز: {PASSPORT}\n- تأشيرة: {VISA}\n- غرفة 907")
    assert (private.passport, private.visa) == ((PASSPORT,), (VISA,))
    assert "907" in safe


def test_the_rest_of_the_message_is_left_as_it_was():
    safe, _ = redact(f"الحاج نبيل 😔 جواز {PASSPORT} غرفة 907")
    assert safe == "الحاج نبيل 😔 جواز [رقم جواز] غرفة 907"


def test_printing_the_private_numbers_never_shows_them():
    _, private = redact(f"جواز {PASSPORT} تأشيرة {VISA}")
    for shown in (repr(private), str(private), f"{private}"):
        assert PASSPORT not in shown and VISA not in shown
    assert "1" in repr(private)  # it says how many there are, not what they are


# --- the request to the model ----------------------------------------------------


def good_answer() -> dict:
    return {
        "type": "nusuk_card", "hotel": "", "location_kind": "none", "number_words": "", "location_number": "",
        "pilgrim_name": "", "risks": [], "partial_words": "", "confidence": "high",
    }  # fmt: skip


def client_recording(sent: list) -> anthropic.Anthropic:
    def handler(request):
        sent.append(request)
        return httpx2.Response(
            200,
            json={
                "id": "msg_test", "type": "message", "role": "assistant", "model": "claude-haiku-5-5",
                "content": [{"type": "text", "text": json.dumps(good_answer())}],
                "stop_reason": "end_turn", "stop_sequence": None,
                "usage": {"input_tokens": 900, "output_tokens": 90},
            },
        )  # fmt: skip

    return anthropic.Anthropic(
        api_key="test-key", max_retries=0, http_client=anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(handler))
    )


@pytest.mark.parametrize(
    "message",
    [
        f"الحاج نبيل ضيع بطاقة نسك، جواز {PASSPORT} وتأشيرة {VISA}",
        "الحاج نبيل ضيع بطاقة نسك، جواز X٠٠١٢٣٤٥ وتأشيرة ٩٩٩٠٠٠١٢٣٤",
        f"نبيل\nبطاقة نسك\n{PASSPORT}\n{VISA}",
    ],
)
def test_the_request_to_the_model_never_contains_a_passport_or_visa_number(message):
    sent = []
    understand(message, client_recording(sent))
    assert len(sent) == 1
    body = sent[0].content.decode("utf-8")
    unescaped = json.dumps(json.loads(body), ensure_ascii=False)
    for secret in (PASSPORT, VISA, "0012345", "٠٠١٢٣٤٥", "٩٩٩٠٠٠١٢٣٤"):
        assert secret not in body and secret not in unescaped


def test_the_report_says_that_the_numbers_were_given_without_holding_them():
    report = understand(f"الحاج نبيل ضيع بطاقة نسك، جواز {PASSPORT} وتأشيرة {VISA}", client_recording([]))
    assert report.has_passport_number is True and report.has_visa_number is True
    assert PASSPORT not in repr(report) and VISA not in repr(report)


def test_a_report_without_such_numbers_says_so():
    report = understand("الحاج نبيل ضيع بطاقة نسك", client_recording([]))
    assert report.has_passport_number is False and report.has_visa_number is False
