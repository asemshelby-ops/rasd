"""Ask-back: when a report lacks something it needs, ask the sender ONE short question.

    question = ask_back(report)                  # None when nothing needs asking
    report = answer(report, question, reply)     # the reply fills the SAME report

A report gets at most one question in its life. Where the answer is one of a
few known things, the question carries tap-buttons (options). No AI in here.
"""

import re
from dataclasses import dataclass, replace

from rasd.numbers import normalise, spoken_number
from rasd.privacy import OTHER_MARK, PASSPORT_MARK, VISA_MARK, redact
from rasd.routing import HOTELS, NUMBERED_PLACES, match_hotel, missing_requirements, near_hotel
from rasd.schema import TYPES
from rasd.text import to_western_digits
from rasd.understand import Understanding, settle

YES, NO = "نعم", "لا"

# The types a sender can pick when asked what the problem is.
TYPE_BUTTONS = {label: code for code, label in TYPES.items() if code not in ("unclear", "not_a_report")}

_FLOOR_WORDS = {"دور", "الدور", "طابق", "الطابق", "منزل"}
_ELEVATOR_WORDS = {"مصعد", "المصعد", "اصنصير", "الاصنصير", "اسانسير", "الاسانسير", "لفٹ"}
_ROOM_WORDS = {"غرفه", "الغرفه", "غرفته", "غرفتها", "روم", "room", "جناح", "الجناح", "رقم", "رقمها", "كمره"}
# Words that show the sender does not know, or will answer later. Such a reply is not an answer.
_NOT_AN_ANSWER = {
    "ما", "مدري", "ماادري", "مادري", "لا", "مو", "مش", "مجهول", "اعرف", "نعرف", "يعرف", "ادري", "ندري",
    "بعدين", "لحظه", "دقيقه", "دقايق", "اسال", "اسالو", "اقول", "نقول", "المشرف", "شوي", "؟", "?",
}  # fmt: skip
_LONGEST_PLACE_NUMBER = 5  # digits: a longer number is a phone or a document, not a room
_NUMBER_LABELS = {"جواز", "الجواز", "جوازه", "رقم", "تاشيره", "التاشيره", "فيزا", "passport", "visa"}


@dataclass(frozen=True)
class Question:
    field: str  # what the answer fills: "type", "place", "hotel", "hotel_confirm" or "name"
    text: str  # the question, in Arabic
    options: tuple[str, ...] = ()  # tap-button answers; empty means the sender types or says the answer


def ask_back(report: Understanding) -> Question | None:
    """The one question to put to the sender of this report, or None."""
    if report.asked or not report.is_report or "not_understood" in report.reasons:
        return None
    if report.type == "unclear":
        return Question("type", "ما المشكلة؟", tuple(TYPE_BUTTONS))
    if "hotel_near_match" in report.reasons and near_hotel(report.hotel):
        return Question("hotel_confirm", f"هل تقصد فندق {near_hotel(report.hotel)}؟", (YES, NO))
    missing = missing_requirements(
        report.type, report.hotel, report.loc_kind, report.loc_number, report.pilgrim_name
    )
    if "place" in missing:
        return Question("place", "ما رقم الغرفة أو الدور؟")
    if "hotel_or_place" in missing:
        return Question("hotel", "في أي فندق؟", tuple(HOTELS))
    if "who" in missing:
        return Question("name", "ما اسم الحاج؟")
    return None


def mark_asked(report: Understanding) -> Understanding:
    """Records that the question was sent, so that the report is never asked again."""
    return replace(report, asked=True)


def answer(report: Understanding, question: Question, reply: str, stage: str | None = None) -> Understanding:
    """Fills the answered field of the same report and works out its owner, priority and flag again.

    A reply we cannot use changes nothing: the report stays with the supervisor.
    """
    changes = {}
    if question.field == "type":
        if reply.strip() in TYPE_BUTTONS:
            changes["type"] = TYPE_BUTTONS[reply.strip()]
    elif question.field == "place":
        changes = _place_in(reply, report.loc_kind)
    elif question.field == "hotel":
        hotel = match_hotel(reply)
        if hotel:
            changes["hotel"] = hotel
    elif question.field == "hotel_confirm":
        # Only a tap decides. "نعم" takes the hotel of the list; "لا" keeps the name as written.
        if reply.strip() in (YES, NO):
            changes["reasons"] = tuple(reason for reason in report.reasons if reason != "hotel_near_match")
        if reply.strip() == YES:
            changes["hotel"] = near_hotel(report.hotel)
    elif question.field == "name":
        name = _name_in(reply)
        if name:
            changes["pilgrim_name"] = name
    return settle(replace(report, asked=True, **changes), stage)


def _is_not_an_answer(reply: str) -> bool:
    return bool(set(normalise(reply).replace("?", " ? ").replace("؟", " ؟ ").split()) & _NOT_AN_ANSWER)


def _place_in(reply: str, current_kind: str) -> dict:
    """The room, floor or elevator a reply gives: {"loc_kind": ..., "loc_number": ...}, or {}.

    A number counts only when the reply is the number alone, or names the place
    it belongs to ("غرفة 305", "الدور 3"). "بعد 5 دقايق" is not a room, and a
    passport or phone number in the reply is taken out first.
    """
    text = to_western_digits(redact(reply)[0])
    words = normalise(text).split()
    floors, elevators = set(words) & _FLOOR_WORDS, set(words) & _ELEVATOR_WORDS
    digits = [number for number in re.findall(r"[0-9]+", text) if len(number) <= _LONGEST_PLACE_NUMBER]
    if digits:
        only_the_number = len(words) == 1
        if not (only_the_number or floors or elevators or set(words) & _ROOM_WORDS) or _is_not_an_answer(text):
            return {}
        number = digits[0]
    else:
        number = spoken_number(reply)
        if not number:
            return {}
    if floors:
        kind = "floor"
    elif elevators:
        kind = "elevator"
    else:
        kind = current_kind if current_kind in NUMBERED_PLACES else "room"
    return {"loc_kind": kind, "loc_number": number}


def _name_in(reply: str) -> str:
    """The name in a reply, without any passport or visa number typed after it. "" when the reply is not a name."""
    safe, _ = redact(reply)
    for mark in (PASSPORT_MARK, VISA_MARK, OTHER_MARK):
        safe = safe.replace(mark, " ")
    words = safe.split()
    while words and normalise(words[-1]).lower() in _NUMBER_LABELS:
        words.pop()
    name = " ".join(words)
    if _is_not_an_answer(name) or not any(character.isalpha() for character in name) or len(words) > 6:
        return ""
    return name
