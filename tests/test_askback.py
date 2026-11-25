"""Ask-back: when a report lacks something it needs, the sender gets ONE short question.

The reply fills the same report. It never opens a second one.
"""

from rasd.askback import Question, answer, ask_back, mark_asked
from rasd.routing import HOTELS
from rasd.schema import TYPES
from rasd.understand import Reading, build_report


def report_from(message: str, **fields):
    base = dict(
        type="water", hotel="", location_kind="none", number_words="", location_number="", pilgrim_name="",
        risks=[], partial_words="", confidence="high",
    )  # fmt: skip
    base.update(fields)
    return build_report(message, Reading(**base))


COMPLETE = report_from("ما في موية في غرفة 907", location_kind="room", number_words="907", location_number="907")
FAULT_NO_ROOM = report_from("الموية مقطوعة في برج السكينة", hotel="برج السكينة")
CARD_NO_NAME = report_from("حاج ضيّع بطاقة نسك في برج السكينة", type="nusuk_card", hotel="برج السكينة")
CARD_NOWHERE = report_from("نبيل سعد ضيّع بطاقة نسك", type="nusuk_card", pilgrim_name="نبيل سعد")
UNCLEAR = report_from("في مشكلة في غرفة 907", type="unclear", location_kind="room", number_words="907", location_number="907")


# --- which question -----------------------------------------------------------------


def test_a_complete_report_gets_no_question():
    assert ask_back(COMPLETE) is None


def test_a_fault_without_a_room_or_floor_is_asked_for_it():
    question = ask_back(FAULT_NO_ROOM)
    assert question.field == "place"
    assert question.options == ()


def test_a_report_that_does_not_say_whose_card_it_is_is_asked_for_the_pilgrims_name():
    assert ask_back(CARD_NO_NAME).field == "name"


def test_a_report_with_no_hotel_and_no_room_is_asked_for_the_hotel_with_tap_buttons():
    question = ask_back(CARD_NOWHERE)
    assert question.field == "hotel"
    assert question.options == tuple(HOTELS)


def test_an_unclear_report_is_asked_what_the_problem_is_with_one_button_per_type():
    question = ask_back(UNCLEAR)
    assert question.field == "type"
    assert set(question.options) == {label for code, label in TYPES.items() if code not in ("unclear", "not_a_report")}


def test_only_one_thing_is_asked_even_when_several_are_missing():
    nothing_known = report_from("في مشكلة", type="unclear")
    assert ask_back(nothing_known).field == "type"
    card = report_from("حاج ضيّع بطاقة نسك", type="nusuk_card")  # no hotel, no name
    assert ask_back(card).field == "hotel"


def test_every_question_is_one_short_arabic_sentence():
    for report in (FAULT_NO_ROOM, CARD_NO_NAME, CARD_NOWHERE, UNCLEAR):
        text = ask_back(report).text
        assert text.endswith("؟") and len(text) <= 40 and "\n" not in text


def test_a_message_that_is_not_a_report_gets_no_question():
    chat = report_from("صباح الخير", type="not_a_report")
    assert ask_back(chat) is None


def test_a_report_the_model_could_not_read_gets_no_question():
    from rasd.understand import understand

    unread = understand("", client=None)
    assert ask_back(unread) is None


def test_a_photo_with_no_words_is_asked_what_the_problem_is():
    from rasd.understand import understand

    photo = understand("", client=None, photo_attached=True)
    assert ask_back(photo).field == "type"


def test_a_report_is_never_asked_twice():
    assert ask_back(mark_asked(FAULT_NO_ROOM)) is None
    completed = answer(CARD_NOWHERE, ask_back(CARD_NOWHERE), HOTELS[0])
    assert ask_back(completed) is None


# --- the reply completes the same report ---------------------------------------------


def test_a_room_number_in_digits_completes_the_report():
    done = answer(FAULT_NO_ROOM, ask_back(FAULT_NO_ROOM), "غرفة ٩٠٧")
    assert (done.loc_kind, done.loc_number) == ("room", "907")
    assert done.needs_confirmation is False
    assert done.reasons == ()


def test_a_room_number_said_in_words_completes_the_report():
    done = answer(FAULT_NO_ROOM, ask_back(FAULT_NO_ROOM), "تسعمية وسبعة")
    assert (done.loc_kind, done.loc_number) == ("room", "907")


def test_a_floor_in_the_reply_is_a_floor():
    done = answer(FAULT_NO_ROOM, ask_back(FAULT_NO_ROOM), "الدور التاسع")
    assert (done.loc_kind, done.loc_number) == ("floor", "9")


def test_a_reply_with_no_number_leaves_the_report_for_the_supervisor():
    done = answer(FAULT_NO_ROOM, ask_back(FAULT_NO_ROOM), "ما أدري والله")
    assert done.loc_number is None
    assert done.reasons == ("no_location",)
    assert done.asked is True


def test_a_tapped_hotel_completes_the_report():
    done = answer(CARD_NOWHERE, ask_back(CARD_NOWHERE), HOTELS[1])
    assert done.hotel == HOTELS[1]
    assert done.needs_confirmation is False


def test_a_typed_hotel_is_recognised_or_kept_as_written():
    assert answer(CARD_NOWHERE, ask_back(CARD_NOWHERE), "فندق برج السكينه").hotel == "برج السكينة"
    assert answer(CARD_NOWHERE, ask_back(CARD_NOWHERE), "قصر الغيم").hotel == "قصر الغيم"


def test_a_name_completes_the_report():
    done = answer(CARD_NO_NAME, ask_back(CARD_NO_NAME), " منصور خليل ")
    assert done.pilgrim_name == "منصور خليل"
    assert done.needs_confirmation is False


def test_a_passport_number_typed_with_the_name_is_not_kept_in_the_name():
    done = answer(CARD_NO_NAME, ask_back(CARD_NO_NAME), "منصور خليل جواز X0012345")
    assert "X0012345" not in done.pilgrim_name
    assert done.pilgrim_name.startswith("منصور خليل")


def test_a_tapped_type_completes_the_report_with_its_owner_and_priority():
    done = answer(UNCLEAR, ask_back(UNCLEAR), TYPES["ac"])
    assert done.type == "ac"
    assert done.owner == "maintenance"
    assert done.urgency == "urgent"
    assert done.needs_confirmation is False


def test_a_type_reply_that_is_not_one_of_the_buttons_leaves_the_report_unclear():
    done = answer(UNCLEAR, ask_back(UNCLEAR), "مدري")
    assert done.type == "unclear" and done.needs_confirmation is True


def test_the_reply_changes_only_the_field_that_was_asked():
    done = answer(CARD_NO_NAME, ask_back(CARD_NO_NAME), "منصور خليل")
    assert (done.type, done.hotel, done.loc_kind, done.urgency) == (
        CARD_NO_NAME.type, CARD_NO_NAME.hotel, CARD_NO_NAME.loc_kind, CARD_NO_NAME.urgency,
    )  # fmt: skip
    assert CARD_NO_NAME.pilgrim_name is None  # the report we started from was not changed in place


def test_other_reasons_to_ask_the_supervisor_stay_after_the_reply():
    unsure = report_from("الموية مقطوعة في برج السكينة", hotel="برج السكينة", confidence="low")
    done = answer(unsure, ask_back(unsure), "907")
    assert done.reasons == ("low_confidence",)
    assert done.needs_confirmation is True


def test_a_question_is_a_small_plain_object():
    assert Question("place", "ما رقم الغرفة أو الدور؟") == Question("place", "ما رقم الغرفة أو الدور؟", ())
