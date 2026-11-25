"""Who owns each type of report, how urgent it is, and how long there is to close it.

These are plain tables that the team edits by hand. The AI model does not choose
the owner, the priority or the deadline. It only reads the message.

How the priority of a report is worked out (priority_for, at the bottom):
  1. the type gives the default            PRIORITY_BY_TYPE
  2. the journey stage may change it       PRIORITY_IN_STAGE
  3. a fault the message says is only partial goes one level down
  4. every risk the message states in words raises it one level, up to critical

The priority table is the team's decision, made after a field review. It follows
what a problem means for the pilgrim at each point of the journey. It was not
fitted to the test reports.
"""

from rasd.numbers import normalise, unglued
from rasd.schema import RISKS, STAGES, URGENCIES

OWNER_BY_TYPE = {
    "lost_pilgrim": "pilgrim_affairs",
    "health": "pilgrim_affairs",
    "nusuk_card": "pilgrim_affairs",
    "no_nusuk_card": "pilgrim_affairs",
    "forgot_credentials": "pilgrim_affairs",
    "luggage": "luggage_team",
    "ac": "maintenance",
    "water": "maintenance",
    "cleaning": "housekeeping",
    "power_elevator": "maintenance",
    "gifts": "pilgrim_affairs",
    "unclear": "supervisor",
    "not_a_report": "nobody",
}

# The default priority of each type of report.
PRIORITY_BY_TYPE = {
    "lost_pilgrim": "critical",
    "health": "critical",
    "nusuk_card": "urgent",
    "no_nusuk_card": "urgent",
    "forgot_credentials": "medium",
    "ac": "urgent",
    "water": "urgent",
    "power_elevator": "urgent",
    "luggage": "medium",
    "cleaning": "normal",
    "gifts": "normal",
    "unclear": "urgent",  # nobody knows what it is yet, so it may be anything
    "not_a_report": "normal",  # never shown: a message that is not a report has no priority
}

# The types that are faults in the building. Only these can be "partial".
FAULT_TYPES = ("ac", "water", "power_elevator")

# The stage of the journey the pilgrims are in now. The operations room changes
# it by hand: arrival, makkah, hajj or departure. (In Phase 2 this becomes a
# control on the board.)
CURRENT_STAGE = "makkah"

# What a stage changes. During the Hajj days the Nusuk card is needed to enter
# the holy sites and the transport, so losing it is critical.
PRIORITY_IN_STAGE = {
    "hajj": {"nusuk_card": "critical", "no_nusuk_card": "critical"},
}

# ---------------------------------------------------------------------------
# Hotels
# ---------------------------------------------------------------------------

# SAMPLE NAMES. These hotels are invented. Replace them with the company's own
# hotels: the names are the tap-buttons of the question "which hotel?".
HOTELS = ["واحة الروضة", "برج السكينة", "دار المنارة", "نزل الياسمين"]
HOTELS_ARE_SAMPLE_DATA = True

_HOTEL_WORDS = {"فندق", "الفندق", "بفندق", "hotel", "هوتيل", "اوتيل", "هوٹل"}
_URDU_LETTERS = str.maketrans({"ک": "ك", "ی": "ي", "ہ": "ه", "ھ": "ه", "ے": "ي"})


def _folded(text: str) -> list[str]:
    """The words of a hotel name with one spelling per letter, Arabic or Urdu, without the word "hotel"."""
    return [word for word in normalise(text.translate(_URDU_LETTERS)).lower().split() if word not in _HOTEL_WORDS]


def match_hotel(text: str) -> str | None:
    """The hotel a piece of text names: one of HOTELS when we know it, otherwise the name as written.

    None when the text names no hotel.
    """
    words = _folded(text)
    if not words:
        return None
    names = {hotel: _folded(hotel) for hotel in HOTELS}
    # The whole name of a hotel we know is in the text. A short word may be glued
    # to the front of the name: "بدار المنارة" (in Dar al-Manara).
    for hotel, name in names.items():
        for start in range(len(words) - len(name) + 1):
            if name[0] in unglued(words[start]) and words[start + 1 : start + len(name)] == name[1:]:
                return hotel
    # The text is a part of the name of exactly one hotel we know: people often
    # leave out a first word such as "نزل" or "برج". A part two hotels share is not guessed.
    parts = [f" {' '.join([first] + words[1:])} " for first in unglued(words[0])]
    partly = [hotel for hotel, name in names.items() if any(part in f" {' '.join(name)} " for part in parts)]
    if len(partly) == 1:
        return partly[0]
    written = [word for word in text.split() if _folded(word)]
    return " ".join(written)


# ---------------------------------------------------------------------------
# What a report needs before it can go to its owner
# ---------------------------------------------------------------------------

# Places that are identified by a number. Without the number nobody can be sent there.
NUMBERED_PLACES = ("room", "elevator", "floor")

# place          = a numbered room, floor or elevator, or a named common area
# hotel_or_place = a hotel, or a place as above
# who            = the pilgrim's name, or a numbered place where to find them
REQUIRED_BY_TYPE = {
    "lost_pilgrim": ("hotel_or_place",),
    "health": ("hotel_or_place",),
    "nusuk_card": ("hotel_or_place", "who"),
    "no_nusuk_card": ("hotel_or_place", "who"),
    "forgot_credentials": ("hotel_or_place", "who"),
    "luggage": ("hotel_or_place", "who"),
    "ac": ("place",),
    "water": ("place",),
    "cleaning": ("place",),
    "power_elevator": ("place",),
    "gifts": ("hotel_or_place", "who"),
    "unclear": (),
    "not_a_report": (),
}


def missing_requirements(type: str, hotel, loc_kind: str, loc_number, pilgrim_name) -> tuple[str, ...]:
    """What a report of this type still lacks, in the order of REQUIRED_BY_TYPE."""
    numbered = loc_kind in NUMBERED_PLACES and loc_number is not None
    placed = numbered or loc_kind == "common_area"
    have = {
        "place": placed,
        "hotel_or_place": bool(hotel) or placed,
        "who": bool(pilgrim_name) or numbered,
    }
    return tuple(need for need in REQUIRED_BY_TYPE[type] if not have[need])


# ---------------------------------------------------------------------------
# Checklists: what the owner collects or does for each type
# ---------------------------------------------------------------------------

CHECKLISTS = {
    "lost_pilgrim": (
        "اسم الحاج إن عُرف، أو وصفه",
        "اللغة التي يتكلمها",
        "أين هو الآن، أو أين شوهد آخر مرة ومتى",
        "شركته وفندقه إن عُرفا",
        "رقم جوال له أو لمرافقه",
    ),
    "health": (
        "اسم الحاج",
        "الفندق والغرفة",
        "ما الذي يشكو منه",
        "هل هو واعٍ ويتنفس",
        "أمراضه المزمنة وأدويته",
        "هل أُبلغ الفريق الطبي أو الإسعاف",
    ),
    "nusuk_card": (
        "الاسم الكامل كما في الجواز",
        "رقم التأشيرة",
        "رقم الجواز",
        "مكان الفقد",
        "تاريخ الفقد ووقته",
        "الشركة والفندق والغرفة",
    ),
    "no_nusuk_card": (
        "الاسم الكامل كما في الجواز",
        "رقم التأشيرة",
        "رقم الجواز",
        "تاريخ الوصول",
        "الشركة والفندق والغرفة",
    ),
    "forgot_credentials": (
        "الاسم الكامل كما في الجواز",
        "ما الذي نسيه: كلمة مرور التطبيق أم رقم الجواز",
        "رقم الجوال المسجّل في التطبيق",
        "الشركة والفندق والغرفة",
    ),
    "luggage": (
        "اسم الحاج",
        "الفندق والغرفة",
        "عدد الحقائب الناقصة ووصفها",
        "رقم الرحلة وتاريخ الوصول",
        "رقم ملصق الحقيبة إن وُجد",
    ),
    "ac": ("الفندق", "الغرفة أو الدور", "ما العطل بالضبط", "منذ متى", "هل في الغرفة مريض أو كبير في السن"),
    "water": ("الفندق", "الغرفة أو الدور", "ما العطل بالضبط", "منذ متى", "هل في الغرفة مريض أو كبير في السن"),
    "cleaning": ("الفندق", "الغرفة", "ما المطلوب: تنظيف أم مناشف أم مفارش"),
    "power_elevator": (
        "الفندق",
        "الغرفة أو الدور أو رقم المصعد",
        "ما العطل بالضبط",
        "منذ متى",
        "هل أحد عالق أو في خطر",
    ),
    "gifts": ("اسم الحاج أو الغرفة أو الدور", "الفندق", "ما الذي لم يُستلم", "تاريخ التوزيع"),
    "unclear": ("ما المشكلة", "أين", "من الحاج"),
    "not_a_report": (),
}

# TRIAL VALUES, in both tables below. These minutes are not measured and do not
# come from a real service agreement. Replace them with the company's real
# targets, and label them as trial data wherever they are shown until then.

# Minutes to ACKNOWLEDGE a report: someone says "I am on it". Only critical
# reports have this first step.
ACKNOWLEDGE_MINUTES = {
    "critical": 5,
}

# Minutes to CLOSE a report.
DEADLINE_MINUTES = {
    "critical": 30,
    "urgent": 15,
    "medium": 60,
    "normal": 180,
}
DEADLINES_ARE_SAMPLE_DATA = True


def priority_for(type: str, risks, stage: str, partial: bool = False) -> str:
    """The priority of a report: a code from schema.URGENCIES.

    type is a code from schema.TYPES, risks are codes from schema.RISKS (the
    risks the message states), stage is a code from schema.STAGES, and partial
    is True when the message itself says the fault is only partial.
    """
    if stage not in STAGES:
        raise ValueError(f"'{stage}' is not a journey stage. Allowed: {', '.join(STAGES)}")
    unknown = [risk for risk in risks if risk not in RISKS]
    if unknown:
        raise ValueError(f"'{unknown[0]}' is not a known risk. Allowed: {', '.join(RISKS)}")

    levels = list(URGENCIES)  # the most urgent first
    default = PRIORITY_IN_STAGE.get(stage, {}).get(type, PRIORITY_BY_TYPE[type])
    steps_down = 1 if partial and type in FAULT_TYPES else 0
    steps_up = len(set(risks))
    position = levels.index(default) + steps_down - steps_up
    return levels[min(max(position, 0), len(levels) - 1)]
