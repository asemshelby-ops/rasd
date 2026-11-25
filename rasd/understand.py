"""The understanding function: the text of a staff message -> a report.

    report = understand("...", client)

Who decides what:
  - The AI model READS the message: type, place, number, the risks the message
    states, and how confident it is.
  - Our tables in routing.py DECIDE the owner, the priority and the deadline.
    The model is never asked how urgent a report is.
  - Our own code CHECKS the room number (numbers.py) and the words of each risk,
    and decides whether the report needs the supervisor to confirm it.

If the model cannot be reached, refuses, or gives no answer, the result is still
a report: it goes to the supervisor, flagged, so that no message is ever lost.
"""

import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

import anthropic
import pydantic
from dotenv import load_dotenv

from rasd import routing
from rasd.numbers import (
    HUNDRED_ENDINGS,
    TEEN_ENDINGS,
    as_written,
    contains_name,
    contains_number,
    contains_words,
    contains_words_in_order,
    hundred_spellings,
    spoken_number,
    teen_spellings,
)
from rasd.privacy import OTHER_MARK, PASSPORT_MARK, VISA_MARK, PrivateNumbers, redact
from rasd.routing import (
    ACKNOWLEDGE_MINUTES,
    DEADLINE_MINUTES,
    FAULT_TYPES,
    NUMBERED_PLACES,
    OWNER_BY_TYPE,
    match_hotel,
    missing_requirements,
    priority_for,
)
from rasd.schema import CONFIDENCES, LOCATION_KINDS, RISKS, TYPES
from rasd.text import to_western_digits

DEFAULT_MODEL = "claude-haiku-5-5"
KEY_VARIABLE = "RASD_CLAUDE_KEY"
PROJECT_DIR = Path(__file__).resolve().parent.parent

# How hard the model thinks before answering: low, medium or high.
# Higher is slower and costs more output tokens.
EFFORT = "medium"
# The most tokens one reply may use, thinking included. The answer itself is small.
MAX_TOKENS = 4000


# ---------------------------------------------------------------------------
# What we ask the model
# ---------------------------------------------------------------------------

# The dialect words for 11 to 19, one line per number: "- 12: اثنعش، ثنعش، طنعش، ...".
# The list comes from numbers.py, so our parser and the model know the same words.
TEEN_TABLE = "\n".join(f"- {number}: {'، '.join(words)}" for number, words in teen_spellings().items())
# The same for the hundreds: "- 600: ستمية".
HUNDRED_TABLE = "\n".join(f"- {number}: {'، '.join(words)}" for number, words in hundred_spellings().items())
OTHER_HUNDRED_ENDINGS = "، ".join(as_written(ending) for ending in HUNDRED_ENDINGS[1:])

# Rule for this prompt: never paste benchmark reports or their room numbers in
# here as examples. tests/test_understand.py checks it.
SYSTEM_PROMPT = f"""\
You read short messages from the staff of a company that serves Hajj pilgrims in \
several hotels. Most messages report a problem a pilgrim has. They come from \
staff phones into one busy group, typed or spoken and written down by a \
speech-to-text program, so they are informal and messy: the pilgrim's name, the \
problem, the hotel and the room may come in any order, on separate lines, with \
bullets, dashes or emojis, and with small mistakes. Messages are in Saudi or \
Palestinian Arabic dialect, or in Urdu.

Read the whole message and fill in the fields below. Use only what the message \
says. The report goes to a worker who acts on it, and a wrong room number sends \
that worker to the wrong door. So when the message does not state something, \
leave it empty or answer unclear instead of guessing.

A token such as {PASSPORT_MARK}, {VISA_MARK} or {OTHER_MARK} stands for a number \
that was hidden before the message reached you. It is never a room number, and \
you never copy it into a field.

type - what the problem is:
- lost_pilgrim: a pilgrim is lost or missing, or cannot communicate (nobody \
understands their language, or they cannot say who they are or where they stay)
- health: a pilgrim is sick, hurt or in a medical emergency, and that is what the \
message reports
- nusuk_card: a pilgrim's Nusuk card (the Hajj permit card) is lost or damaged
- no_nusuk_card: a pilgrim has no Nusuk card at all: it was never issued to them \
or they never received it
- forgot_credentials: a pilgrim forgot the password of their app, or forgot \
their passport number
- luggage: bags that did not arrive, or a missing bag
- ac: a fault in the air conditioning
- water: no water, or a fault in the water supply
- cleaning: the room needs cleaning, towels or bed linen
- power_elevator: an electricity fault (power, lights, sockets) or an elevator fault
- gifts: gifts, meals or other distributions that pilgrims did not receive
- unclear: the message reports a problem but does not say what it is, or it is \
none of the above
- not_a_report: the message reports no problem of a pilgrim. For example staff \
attendance, notes of a meeting, a file sent with no request, a greeting or small \
talk, or a reply to an earlier message such as "found it", "done" or a thumbs-up
When the message reports a fault or a loss and also mentions a sick or elderly \
pilgrim, the type is the fault or the loss. Use health only when the pilgrim's \
condition is itself what needs help.

hotel - the name of the hotel the message gives, copied as it is written, \
without the word for "hotel". Leave it empty when the message names no hotel.

location_kind - where the problem is inside the hotel. For a pilgrim who is lost \
or sick, or whose card or bag the report is about, it is the place the message \
gives for that pilgrim, such as their room:
- room: one guest room
- elevator: an elevator
- floor: a whole floor, or a shared part of one floor such as its corridor
- common_area: a shared place that has no number, such as the lobby or the restaurant
- none: the message does not say where
If the problem is in one room but the message does not give that room's number, \
answer room and leave the number empty, even when the floor is mentioned. A hotel \
alone is not a location_kind: answer none when the message gives a hotel and no \
room, floor or other place.

number_words - the words or digits that give the number of that room, elevator or \
floor, copied exactly as they are written in the message. Copy only the number, \
not the word for the place. Leave it empty when there is no number.

location_number - the same number in Western digits (0-9). Leave it empty when \
there is no number.

Staff say room numbers in several ways:
- as one number: "خمسمية وستة وثلاثين" is 536. Arabic says the units before the tens.
- digit by digit: "سبعة تسعة صفر" is 790.
- in pieces: "أحدعش ثلاثة وأربعين" is 11 then 43, so 1143. "تسعة أربعطعش" is 9 then 14, so 914.
Each number from 11 to 19 is said as one word, and that word changes with the \
dialect. Find the word in this list and use the number on its line. Do not work \
the number out from how the word sounds:
{TEEN_TABLE}
These words may end in {"، ".join(TEEN_ENDINGS[1:])} instead of {TEEN_ENDINGS[0]}: \
"خمسطعش" and "خمستاشر" are both 15.
Each hundred is said as one word too. Find the word in this list in the same way:
{HUNDRED_TABLE}
From 300 on, these words may end in {OTHER_HUNDRED_ENDINGS} instead of \
{as_written(HUNDRED_ENDINGS[0])}, and the last letter ة may be written ه.
If the speaker corrects the number, use the number they end with.
Other numbers in the message, such as counts, times and durations, are not the location.

pilgrim_name - the name of the pilgrim the report is about, copied as it is \
written, without a title such as الحاج or الحاجة. Leave it empty when the message \
gives no pilgrim's name. The names of staff are not the pilgrim's name.

risks - dangers that the message states in its own words. Most messages state \
none, and then the list is empty. Add one entry for each kind below that the \
message states:
- elderly: the message says a pilgrim is old
- sick: the message says a pilgrim is sick or hurt, or names an illness or a \
symptom a pilgrim has
- medication: the message mentions a pilgrim's medicine
- time_limit: the message gives a time that is running out, such as the group \
leaving soon, a flight, or a rite the pilgrim will miss
- alone_or_lost: the message says a pilgrim is alone, lost, missing or cannot be reached
- danger: the message says people are in immediate physical danger: trapped \
somewhere (for example inside an elevator), or there is fire, smoke, sparks or a \
burning smell
In words, copy the exact words of the message that state the risk. If you cannot \
point to such words, the risk is not stated, so do not add it. Heat, discomfort, a \
long wait, a complaint or an angry pilgrim is not a risk on its own. Do not judge \
how urgent the report is: the team's own table decides that from the type and \
from these risks.

partial_words - only for a fault (air conditioning, water, electricity, \
elevator): the exact words of the message that say the fault is only partial, or \
that the thing still works. For example a tap that drips while the water still \
runs, or one socket out of several that stopped working. Leave it empty when the \
message does not say so. Never decide by yourself that a fault is small.

confidence:
- high: what the message does state is clear
- low: you had to guess something you filled in, or the message contradicts \
itself, or it is too vague to tell what the problem is
A field the message simply does not give (no hotel, no name, no room) is not a \
reason for low confidence: leave that field empty and answer high.
"""


# One risk the message states: its kind, and the words of the message that state it.
class Risk(pydantic.BaseModel):
    kind: Literal[tuple(RISKS)]
    words: str


# What the model reads from one message. The API forces the reply into exactly
# this shape (structured output), so it always parses. The allowed codes come
# straight from schema.py. The model fills the fields from top to bottom, so it
# quotes the number words before it converts them to digits.
# There is no priority field: the model is not asked how urgent a report is.
class Reading(pydantic.BaseModel):
    type: Literal[tuple(TYPES)]
    hotel: str
    location_kind: Literal[tuple(LOCATION_KINDS)]
    number_words: str
    location_number: str
    pilgrim_name: str
    risks: list[Risk]
    partial_words: str
    confidence: Literal[tuple(CONFIDENCES)]


# ---------------------------------------------------------------------------
# The report we build from the model's reading
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Understanding:
    type: str  # a code from schema.TYPES
    loc_kind: str  # a code from schema.LOCATION_KINDS
    loc_number: str | None  # digits, or None when the place has no number
    urgency: str  # the priority: a code from schema.URGENCIES, worked out by routing.priority_for
    owner: str  # a code from schema.OWNERS, taken from routing.py
    deadline_minutes: int  # taken from routing.py (sample values for now)
    confidence: str  # a code from schema.CONFIDENCES
    needs_confirmation: bool  # True = the supervisor must confirm before it is trusted
    reasons: tuple[str, ...]  # why it is flagged: codes from schema.FLAG_REASONS
    number_words: str = ""  # the words the model read the number from
    risks: tuple[str, ...] = ()  # the risks the message states: codes from schema.RISKS
    risk_words: tuple[str, ...] = ()  # the words the model quoted for each risk, in the same order
    partial: bool = False  # True when the message itself says the fault is only partial
    partial_words: str = ""  # the words the model quoted for that
    acknowledge_minutes: int | None = None  # minutes to say "I am on it"; only critical reports have this step
    hotel: str | None = None  # the hotel's name: one of routing.HOTELS when we know it
    pilgrim_name: str | None = None  # NEVER show the full name on the big screen: use display.screen_label
    photo_attached: bool = False  # only that a photo came with the message; the photo is never analysed here
    has_passport_number: bool = False  # the message gave one; the number itself is kept apart (privacy.py)
    has_visa_number: bool = False
    asked: bool = False  # True once the one allowed question was put to the sender (askback.py)
    input_tokens: int = 0  # what the call used, for the cost
    output_tokens: int = 0
    error: str | None = None  # for developers: why the model gave no answer

    @property
    def is_report(self) -> bool:
        """False for a message that is not a report at all (attendance, chat, a reply)."""
        return self.type != "not_a_report"


def _number_is_confirmed(message: str, quote: str, number: str) -> bool:
    """Our own second reading of the room number. It is confirmed when either:

    - the message has that very number written in digits, or
    - the words the model quoted are really in the message, and our parser reads
      the same number from those words.
    """
    if contains_number(message, number):
        return True
    return contains_words(message, quote) and spoken_number(quote) == number


# Reasons that come from what the report still lacks. They are worked out again
# whenever a field is filled in later (askback.py); the other reasons are not.
REQUIREMENT_REASONS = ("unclear_type", "no_location", "no_pilgrim")


def requirement_reasons(type: str, hotel, loc_kind: str, loc_number, pilgrim_name) -> list[str]:
    """Why a report cannot go to its owner yet: codes from REQUIREMENT_REASONS."""
    reasons = []
    if type == "unclear":
        reasons.append("unclear_type")
    missing = missing_requirements(type, hotel, loc_kind, loc_number, pilgrim_name)
    if "place" in missing or "hotel_or_place" in missing:
        reasons.append("no_location")
    if "who" in missing:
        reasons.append("no_pilgrim")
    return reasons


def settle(report: Understanding, stage: str | None = None) -> Understanding:
    """Works out again everything that follows from a report's fields: owner, priority,
    deadlines and whether the supervisor must confirm it. Use it after a field changed."""
    urgency = priority_for(report.type, report.risks, stage or routing.CURRENT_STAGE, report.partial)
    kept = [reason for reason in report.reasons if reason not in REQUIREMENT_REASONS]
    reasons = requirement_reasons(report.type, report.hotel, report.loc_kind, report.loc_number, report.pilgrim_name)
    reasons += kept
    return replace(
        report,
        urgency=urgency,
        owner=OWNER_BY_TYPE[report.type],
        deadline_minutes=DEADLINE_MINUTES[urgency],
        acknowledge_minutes=ACKNOWLEDGE_MINUTES.get(urgency),
        needs_confirmation=bool(reasons),
        reasons=tuple(reasons),
    )


def build_report(
    message: str,
    reading: Reading,
    input_tokens: int = 0,
    output_tokens: int = 0,
    stage: str | None = None,
    photo_attached: bool = False,
    private: PrivateNumbers = PrivateNumbers(),
) -> Understanding:
    """Applies our rules to the model's reading. No AI in here.

    stage is the stage of the journey (a code from schema.STAGES). When it is
    not given, the one set in routing.py is used. private holds the numbers
    that were taken out of the message; only the fact that they exist is kept.
    """
    extras = dict(
        photo_attached=photo_attached,
        has_passport_number=bool(private.passport),
        has_visa_number=bool(private.visa),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
    type = reading.type
    if type == "not_a_report":
        if reading.confidence == "high":
            return _not_a_report(**extras)
        # Dropping a real report by mistake is the worst outcome. When the model is
        # not sure the message is nothing, a person looks at it.
        type = "unclear"

    kind = reading.location_kind
    number = "".join(to_western_digits(reading.location_number).split()) or None
    if kind not in NUMBERED_PLACES:
        number = None
    # The hotel and the pilgrim's name are kept only when their words are really in the message.
    hotel = match_hotel(reading.hotel) if contains_name(message, reading.hotel) else None
    name = reading.pilgrim_name.strip() if contains_name(message, reading.pilgrim_name) else None

    # The risks the model says the message states: kind -> the words it quoted.
    quoted = {}
    for risk in reading.risks:
        quoted.setdefault(risk.kind, risk.words)
    risks = tuple(risk for risk in RISKS if risk in quoted)
    # A fault counts as partial only when the words the model quoted for it are really in the message.
    says_partial = bool(reading.partial_words.strip()) and type in FAULT_TYPES
    partial = says_partial and contains_words_in_order(message, reading.partial_words)
    urgency = priority_for(type, risks, stage or routing.CURRENT_STAGE, partial)

    reasons = requirement_reasons(type, hotel, kind, number, name)
    if number is not None and not _number_is_confirmed(message, reading.number_words, number):
        reasons.append("number_not_confirmed")
    # A risk counts even when its words are not found in the message, because the
    # higher priority is the safe side. But then a person must look at the report.
    if any(not contains_words_in_order(message, quoted[risk]) for risk in risks):
        reasons.append("risk_not_confirmed")
    # A lower priority on words that are not in the message would be a guess: the
    # default priority stays, and a person looks at the report.
    if says_partial and not partial:
        reasons.append("partial_not_confirmed")
    if reading.confidence == "low":
        reasons.append("low_confidence")

    return Understanding(
        type=type,
        loc_kind=kind,
        loc_number=number,
        urgency=urgency,
        owner=OWNER_BY_TYPE[type],
        deadline_minutes=DEADLINE_MINUTES[urgency],
        confidence=reading.confidence,
        needs_confirmation=bool(reasons),
        reasons=tuple(reasons),
        number_words=reading.number_words,
        risks=risks,
        risk_words=tuple(quoted[risk] for risk in risks),
        partial=partial,
        partial_words=reading.partial_words if partial else "",
        acknowledge_minutes=ACKNOWLEDGE_MINUTES.get(urgency),
        hotel=hotel,
        pilgrim_name=name or None,
        **extras,
    )


def _not_a_report(**extras) -> Understanding:
    """A message that is not a report: it goes to nobody and never reaches the board."""
    return Understanding(
        type="not_a_report",
        loc_kind="none",
        loc_number=None,
        urgency="normal",
        owner=OWNER_BY_TYPE["not_a_report"],
        deadline_minutes=DEADLINE_MINUTES["normal"],
        confidence="high",
        needs_confirmation=False,
        reasons=(),
        **extras,
    )


def _needs_a_person(reason: str, error: str | None = None, **extras) -> Understanding:
    """A report nobody could classify: straight to the supervisor.

    It is marked urgent because nobody has read it yet, so we cannot rule out
    an emergency. The owner approved this rule.
    """
    urgency = "urgent"
    return Understanding(
        type="unclear",
        loc_kind="none",
        loc_number=None,
        urgency=urgency,
        owner=OWNER_BY_TYPE["unclear"],
        deadline_minutes=DEADLINE_MINUTES[urgency],
        confidence="low",
        needs_confirmation=True,
        reasons=(reason,),
        error=error,
        **extras,
    )


def not_understood(error: str, photo_attached: bool = False) -> Understanding:
    """The report for a message nobody could read (no network, no key): it goes to the supervisor."""
    return _needs_a_person("not_understood", error, photo_attached=photo_attached)


# ---------------------------------------------------------------------------
# Calling the model
# ---------------------------------------------------------------------------


def make_client(env_file: Path = PROJECT_DIR / ".env") -> anthropic.Anthropic:
    """The Claude client, with the key read from RASD_CLAUDE_KEY.

    On a laptop the key is in the .env file; in the cloud it is already set.
    """
    load_dotenv(env_file)
    key = os.environ.get(KEY_VARIABLE, "").strip()
    if not key:
        raise RuntimeError(
            f"{KEY_VARIABLE} is not set. Copy .env.example to .env and put the Claude key in it."
        )
    # A stuck call must not freeze the reception desk: give up after 30 seconds.
    return anthropic.Anthropic(api_key=key, timeout=30.0, max_retries=2)


def ask_model(safe_message: str, client: anthropic.Anthropic, model: str = DEFAULT_MODEL):
    """The one call to Claude: the message goes in, the model's Reading comes back in the reply.

    Raises what the SDK raises. safe_message must already have its passport and visa numbers taken out.
    """
    return client.messages.parse(
        model=model,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": safe_message}],
        output_format=Reading,
        output_config={"effort": EFFORT},
    )


def understand(
    message: str,
    client: anthropic.Anthropic,
    model: str = DEFAULT_MODEL,
    stage: str | None = None,
    photo_attached: bool = False,
) -> Understanding:
    """Turns the text of one staff message into a report. Never raises on a model failure.

    stage is the stage of the journey; when it is not given, the one set in routing.py is used.
    photo_attached only records that a photo came with the message.

    Passport and visa numbers are taken out before the text goes to the model.
    To get those numbers for the pilgrim-affairs record, call privacy.redact(message).
    """
    safe_message, private = redact(message)
    extras = dict(
        photo_attached=photo_attached,
        has_passport_number=bool(private.passport),
        has_visa_number=bool(private.visa),
    )
    if not safe_message.strip():
        if photo_attached:
            return _needs_a_person("unclear_type", **extras)  # a photo and no words: ask what the problem is
        return _needs_a_person("not_understood", "the message is empty", **extras)

    def failed(error: str, input_tokens: int = 0, output_tokens: int = 0) -> Understanding:
        return _needs_a_person(
            "not_understood", error, input_tokens=input_tokens, output_tokens=output_tokens, **extras
        )

    try:
        reply = ask_model(safe_message, client, model)
    except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as e:
        return failed(f"the Claude key was rejected, check {KEY_VARIABLE} ({e.status_code})")
    except anthropic.NotFoundError:
        return failed(f"the model '{model}' was not found")
    except anthropic.RateLimitError:
        return failed("too many requests, the API asked us to slow down")
    except anthropic.APIStatusError as e:
        return failed(f"the API answered with error {e.status_code}: {e.message}")
    except anthropic.APIConnectionError:
        return failed("could not reach the API (network problem or timeout)")
    except pydantic.ValidationError:
        return failed("the reply was not in the expected shape (it may have been cut off)")

    tokens = (reply.usage.input_tokens, reply.usage.output_tokens)
    if reply.stop_reason == "refusal":
        return failed("the model refused to read this message", *tokens)
    if reply.parsed_output is None:
        return failed(f"the model gave no answer (stop reason: {reply.stop_reason})", *tokens)
    return build_report(
        safe_message, reply.parsed_output, *tokens, stage=stage, photo_attached=photo_attached, private=private
    )
