"""The understanding function: the text of a staff message -> a report.

    report = understand("...", client)

Who decides what:
  - The AI model READS the message: type, place, number, urgency, confidence.
  - Our tables in routing.py DECIDE the owner and the deadline.
  - Our own code CHECKS the room number (numbers.py) and decides whether the
    report needs the supervisor to confirm it.

If the model cannot be reached, refuses, or gives no answer, the result is still
a report: it goes to the supervisor, flagged, so that no message is ever lost.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import anthropic
import pydantic
from dotenv import load_dotenv

from rasd.numbers import contains_words, spoken_number
from rasd.routing import DEADLINE_MINUTES, OWNER_BY_TYPE
from rasd.schema import CONFIDENCES, LOCATION_KINDS, TYPES, URGENCIES
from rasd.text import to_western_digits

DEFAULT_MODEL = "claude-haiku-5-5"
KEY_VARIABLE = "RASD_CLAUDE_KEY"
PROJECT_DIR = Path(__file__).resolve().parent.parent

# How hard the model thinks before answering: low, medium or high.
# Higher is slower and costs more output tokens.
EFFORT = "medium"
# The most tokens one reply may use, thinking included. The answer itself is small.
MAX_TOKENS = 4000

# Places that are identified by a number. Without the number nobody can be sent there.
NUMBERED_PLACES = ("room", "elevator", "floor")


# ---------------------------------------------------------------------------
# What we ask the model
# ---------------------------------------------------------------------------

# The team's urgency rule. It is also written in README.md: change both together.
URGENCY_RULE = """\
- urgent: any one of these: danger to safety or health; an elderly or sick pilgrim \
is affected; a pilgrim is about to miss a rite or their group's departure; many \
people are affected at once (a whole floor, or an elevator)
- medium: an essential service has stopped completely for one room or one pilgrim \
(air conditioning, water, electricity, luggage, Nusuk card) and none of the urgent \
conditions apply
- low: everything else: cleaning, partial or minor faults, routine requests"""

# Rule for this prompt: never paste benchmark reports or their room numbers in
# here as examples. tests/test_understand.py checks it.
SYSTEM_PROMPT = f"""\
You read short messages from reception staff in a hotel that houses Hajj pilgrims. \
Each message reports a problem a pilgrim has. The staff member speaks the message \
and a speech-to-text program writes it down, so it is informal and may contain \
small mistakes. Messages are in Saudi or Palestinian Arabic dialect, or in Urdu.

Read the message and fill in the fields below. Use only what the message says. \
The report goes to a worker who acts on it, and a wrong room number sends that \
worker to the wrong door. So when the message does not state something, leave it \
empty or answer unclear instead of guessing.

type - what the problem is:
- nusuk_card: a pilgrim lost their Nusuk card (the Hajj permit card)
- luggage: bags that did not arrive, or a missing bag
- ac: a fault in the air conditioning
- water: no water, or a fault in the water supply
- cleaning: the room needs cleaning, towels or bed linen
- power_elevator: an electricity fault (power, lights, sockets) or an elevator fault
- unclear: the message does not say what the problem is, or it is none of the above

location_kind - where the problem is:
- room: one guest room
- elevator: an elevator
- floor: a whole floor, or a shared part of one floor such as its corridor
- common_area: a shared place that has no number, such as the lobby or the restaurant
- none: the message does not say where
If the problem is in one room but the message does not give that room's number, \
answer room and leave the number empty, even when the floor is mentioned.

number_words - the words or digits that give the number of that room, elevator or \
floor, copied exactly as they are written in the message. Copy only the number, \
not the word for the place. Leave it empty when there is no number.

location_number - the same number in Western digits (0-9). Leave it empty when \
there is no number.

Staff say room numbers in several ways:
- as one number: "خمسمية وستة وثلاثين" is 536. Arabic says the units before the tens.
- digit by digit: "سبعة تسعة صفر" is 790.
- in pieces: "أحدعش ثلاثة وأربعين" is 11 then 43, so 1143. "تسعة أربعطعش" is 9 then 14, so 914.
The numbers 11 to 19 have many dialect spellings.
If the speaker corrects the number, use the number they end with.
Other numbers in the message, such as counts, times and durations, are not the location.

urgency:
{URGENCY_RULE}

confidence:
- high: the message states every field clearly
- low: you had to guess a field, or the message is vague or contradicts itself
"""


# What the model reads from one message. The API forces the reply into exactly
# this shape (structured output), so it always parses. The allowed codes come
# straight from schema.py. The model fills the fields from top to bottom, so it
# quotes the number words before it converts them to digits.
class Reading(pydantic.BaseModel):
    type: Literal[tuple(TYPES)]
    location_kind: Literal[tuple(LOCATION_KINDS)]
    number_words: str
    location_number: str
    urgency: Literal[tuple(URGENCIES)]
    confidence: Literal[tuple(CONFIDENCES)]


# ---------------------------------------------------------------------------
# The report we build from the model's reading
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Understanding:
    type: str  # a code from schema.TYPES
    loc_kind: str  # a code from schema.LOCATION_KINDS
    loc_number: str | None  # digits, or None when the place has no number
    urgency: str  # a code from schema.URGENCIES
    owner: str  # a code from schema.OWNERS, taken from routing.py
    deadline_minutes: int  # taken from routing.py (sample values for now)
    confidence: str  # a code from schema.CONFIDENCES
    needs_confirmation: bool  # True = the supervisor must confirm before it is trusted
    reasons: tuple[str, ...]  # why it is flagged: codes from schema.FLAG_REASONS
    number_words: str = ""  # the words the model read the number from
    input_tokens: int = 0  # what the call used, for the cost
    output_tokens: int = 0
    error: str | None = None  # for developers: why the model gave no answer


def _number_is_confirmed(message: str, quote: str, number: str) -> bool:
    """Our own second reading of the room number. All three must hold:
    the number is digits, the quoted words are really in the message, and our
    parser reads the same number from those words."""
    return number.isdigit() and contains_words(message, quote) and spoken_number(quote) == number


def build_report(message: str, reading: Reading, input_tokens: int = 0, output_tokens: int = 0) -> Understanding:
    """Applies our rules to the model's reading. No AI in here."""
    kind = reading.location_kind
    number = "".join(to_western_digits(reading.location_number).split()) or None
    if kind not in NUMBERED_PLACES:
        number = None

    reasons = []
    if reading.type == "unclear":
        reasons.append("unclear_type")
    if kind == "none" or (kind in NUMBERED_PLACES and number is None):
        reasons.append("no_location")
    if number is not None and not _number_is_confirmed(message, reading.number_words, number):
        reasons.append("number_not_confirmed")
    if reading.confidence == "low":
        reasons.append("low_confidence")

    return Understanding(
        type=reading.type,
        loc_kind=kind,
        loc_number=number,
        urgency=reading.urgency,
        owner=OWNER_BY_TYPE[reading.type],
        deadline_minutes=DEADLINE_MINUTES[reading.urgency],
        confidence=reading.confidence,
        needs_confirmation=bool(reasons),
        reasons=tuple(reasons),
        number_words=reading.number_words,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


def _not_understood(error: str, input_tokens: int = 0, output_tokens: int = 0) -> Understanding:
    """The report we give when the model gave no answer: straight to the supervisor.

    It is marked urgent because nobody has read it yet, so we cannot rule out
    an emergency. The owner approved this rule.
    """
    return Understanding(
        type="unclear",
        loc_kind="none",
        loc_number=None,
        urgency="urgent",
        owner=OWNER_BY_TYPE["unclear"],
        deadline_minutes=DEADLINE_MINUTES["urgent"],
        confidence="low",
        needs_confirmation=True,
        reasons=("not_understood",),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        error=error,
    )


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


def understand(message: str, client: anthropic.Anthropic, model: str = DEFAULT_MODEL) -> Understanding:
    """Turns the text of one staff message into a report. Never raises on a model failure."""
    if not message.strip():
        return _not_understood("the message is empty")

    try:
        reply = client.messages.parse(
            model=model,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": message}],
            output_format=Reading,
            output_config={"effort": EFFORT},
        )
    except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as e:
        return _not_understood(f"the Claude key was rejected, check {KEY_VARIABLE} ({e.status_code})")
    except anthropic.NotFoundError:
        return _not_understood(f"the model '{model}' was not found")
    except anthropic.RateLimitError:
        return _not_understood("too many requests, the API asked us to slow down")
    except anthropic.APIStatusError as e:
        return _not_understood(f"the API answered with error {e.status_code}: {e.message}")
    except anthropic.APIConnectionError:
        return _not_understood("could not reach the API (network problem or timeout)")
    except pydantic.ValidationError:
        return _not_understood("the reply was not in the expected shape (it may have been cut off)")

    tokens = (reply.usage.input_tokens, reply.usage.output_tokens)
    if reply.stop_reason == "refusal":
        return _not_understood("the model refused to read this message", *tokens)
    if reply.parsed_output is None:
        return _not_understood(f"the model gave no answer (stop reason: {reply.stop_reason})", *tokens)
    return build_report(message, reply.parsed_output, *tokens)
