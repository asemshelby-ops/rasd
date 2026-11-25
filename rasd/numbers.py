"""Reads a number the way hotel staff say it and returns its digits.

    "تسعمية وسبعة"  -> "907"      (one number, parts joined with "و")
    "ثلاثة تسعة خمسة" -> "395"      (digit by digit)
    "أحدعش صفر ثمانية" -> "1108"    (said in pieces: 11, 0, 8)

This is our own check on the AI model. The model reads the room number and also
quotes the words it read it from; this file re-reads that quote. If the two
readings differ, the report is flagged for a person to confirm.

The parser is strict on purpose: when it is not sure, it returns None. A wrong
room number is worse than a question to the supervisor.

To teach it a new spelling, add the word to one of the tables below.
Arabic only for now: Urdu number words are not covered.
"""

import re

from rasd.text import to_western_digits

# ---------------------------------------------------------------------------
# 1. Spelling. People write the same word in many ways ("أربعة", "اربعه").
#    normalise() rewrites text so that those spellings become identical.
#    Every word in the tables below is written in this normalised spelling.
# ---------------------------------------------------------------------------

_MARKS = re.compile("[ً-ْٰـ]")  # short vowels and the stretch mark
_SAME_LETTER = str.maketrans(
    {"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ئ": "ي", "ؤ": "و", "ة": "ه"}
)
_PUNCTUATION = re.compile(r"[^\w]+")


def normalise(text: str) -> str:
    """Western digits, one spelling per letter, no punctuation, single spaces."""
    text = to_western_digits(text)
    text = _MARKS.sub("", text)
    text = text.translate(_SAME_LETTER)
    return " ".join(_PUNCTUATION.sub(" ", text).split())


def contains_words(message: str, quote: str) -> bool:
    """True if the quoted words really appear in the message, as whole words."""
    quote = normalise(quote)
    message = f" {normalise(message)} "
    if not quote:
        return False
    # The quote may leave out a leading "و" that is glued to its first word.
    return f" {quote} " in message or f" و{quote} " in message


def contains_number(message: str, number: str) -> bool:
    """True if the message has exactly this number written in digits.

    Arabic and Urdu digits count. "907" is not found inside "1907".
    """
    return number in re.findall(r"[0-9]+", to_western_digits(message))


# ---------------------------------------------------------------------------
# 2. The number words.
# ---------------------------------------------------------------------------

_UNITS = {
    0: "صفر زيرو",
    1: "واحد واحده وحده",
    2: "اثنين اثنان اثنتين ثنين ثنتين اتنين تنين تنتين",
    3: "ثلاثه ثلاث ثلاته تلاته تلات تلاثه",
    4: "اربعه اربع",
    5: "خمسه خمس",
    6: "سته ست",
    7: "سبعه سبع",
    8: "ثمانيه ثماني ثمان تمانيه تماني تمان",
    9: "تسعه تسع",
}

# 11 to 19 have many dialect spellings. Each one is a beginning plus an ending:
# "خمسط" + "عش" = "خمسطعش", "خمست" + "اشر" = "خمستاشر".
_TEEN_BEGINNINGS = {
    11: "احد حد ايد اد",
    12: "اثن ثن طن اطن تن اتن",
    13: "ثلاثط ثلاثت ثلاث ثلاتط ثلاط ثلط ثلتط ثلت تلاتط تلات تلاط تلط تلتط تلت",
    14: "اربعط اربعت اربط ربعط ربعت",
    15: "خمسط خمست خمصط خمصت",
    16: "ستط ستت ست سط",
    17: "سبعط سبعت سبط",
    18: "ثمانط ثمانت ثمنط ثمنت ثمط تمانط تمانت تمنط تمنت تمط",
    19: "تسعط تسعت تسط",
}
TEEN_ENDINGS = "عش عشر اشر اعش اعشر".split()  # the commonest ending comes first


def teen_spellings() -> dict[int, list[str]]:
    """The words for 11 to 19 with the commonest ending: 15 -> ["خمسطعش", "خمستعش", ...].

    The prompt in understand.py shows this list to the model, so a spelling added
    to _TEEN_BEGINNINGS is learned by our parser and by the model together.
    """
    return {
        value: [beginning + TEEN_ENDINGS[0] for beginning in beginnings.split()]
        for value, beginnings in _TEEN_BEGINNINGS.items()
    }

_TENS = {
    20: "عشرين عشرون",
    30: "ثلاثين ثلاثون ثلاتين تلاتين تلاثين",
    40: "اربعين اربعون",
    50: "خمسين خمسون",
    60: "ستين ستون",
    70: "سبعين سبعون",
    80: "ثمانين ثمانون تمانين",
    90: "تسعين تسعون",
}

# 300 to 900 are also a beginning plus an ending: "تسع" + "ميه" = "تسعميه".
_HUNDRED_BEGINNINGS = {
    300: "ثلاث ثلات ثلث تلات تلت",
    400: "اربع ربع",
    500: "خمس خمص",
    600: "ست",
    700: "سبع",
    800: "ثمان ثماني ثمن تمان تماني تمن",
    900: "تسع",
}
_HUNDRED_ENDINGS = "ميه مايه ميت"
_HUNDREDS = {100: "ميه مايه ميت", 200: "ميتين ميتان مايتين مايتان"}

_THOUSANDS = {1000: "الف", 2000: "الفين الفان"}

# "the second", "the fifth": used for floors and elevators.
_ORDINALS = {
    1: "اول اولي حادي",
    2: "ثاني ثانيه تاني تانيه",
    3: "ثالث ثالثه ثالت تالت تالته",
    4: "رابع رابعه",
    5: "خامس خامسه",
    6: "سادس سادسه ساتت",
    7: "سابع سابعه",
    8: "ثامن ثامنه تامن تامنه",
    9: "تاسع تاسعه",
    10: "عاشر عاشره",
}

# Words that name the place. They may sit next to the number and are skipped.
_PLACE_WORDS = set(
    "غرفه الغرفه غرفت رقم نمره روم مصعد المصعد اصنصير الاصنصير اسانسير الاسانسير "
    "دور الدور طابق الطابق جناح الجناح کمرہ کمره نمبر لفٹ منزل".split()
)

# Two-word forms: "خمس مية" (500), "ثلاث آلاف" (3000), "أربعة عشر" (14).
_HUNDRED_WORDS = {"ميه", "مايه"}
_THOUSAND_WORDS = {"الاف", "تالاف", "تلاف"}
_TEN_WORDS = {"عشر", "عشره"}
_FIRST_OF_TEEN = {"احد": 1, "احدي": 1, "اثنا": 2, "اثني": 2}  # "أحد عشر", "اثنا عشر"


def _build_word_table() -> dict[str, tuple[str, int]]:
    """One lookup table: word -> (kind, value). Kinds: unit, teen, tens, hundred, thousand, ordinal."""
    table: dict[str, tuple[str, int]] = {}

    def add(kind: str, value: int, words) -> None:
        for word in words:
            if table.get(word, (kind, value)) != (kind, value):
                raise ValueError(f"numbers.py: the word '{word}' is listed with two different meanings")
            table[word] = (kind, value)

    for value, words in _UNITS.items():
        add("unit", value, words.split())
    add("teen", 10, ["عشره", "عشر"])
    for value, beginnings in _TEEN_BEGINNINGS.items():
        add("teen", value, [b + e for b in beginnings.split() for e in TEEN_ENDINGS])
    for value, words in _TENS.items():
        add("tens", value, words.split())
    for value, words in _HUNDREDS.items():
        add("hundred", value, words.split())
    for value, beginnings in _HUNDRED_BEGINNINGS.items():
        add("hundred", value, [b + e for b in beginnings.split() for e in _HUNDRED_ENDINGS.split()])
    for value, words in _THOUSANDS.items():
        add("thousand", value, words.split())
    for value, words in _ORDINALS.items():
        add("ordinal", value, words.split())
    return table


_WORDS = _build_word_table()


# ---------------------------------------------------------------------------
# 3. Reading.
#    Step A: turn each word into a part: (kind, value, joined).
#            "joined" means the word was linked with "و" to the word before it.
#    Step B: parts linked with "و" are ADDED:        تسعمية + و سبعة   = 907
#    Step C: parts said side by side are JOINED:     "11" "0" "8"      = 1108
# ---------------------------------------------------------------------------


def _look_up(word: str):
    """Returns (kind, value, joined) for one word, or None if it is not a number word."""
    if word.isdigit():
        return ("digits", word, False)
    if word in _WORDS:
        return (*_WORDS[word], False)
    # Try without a leading "و" (and), then without a leading "ال" (the).
    for prefix, joined in (("و", True), ("ال", False), ("وال", True)):
        rest = word[len(prefix):]
        if word.startswith(prefix) and rest in _WORDS:
            return (*_WORDS[rest], joined)
    return None


def _to_parts(words: list[str]):
    """Step A. Returns a list of (kind, value, joined), or None on an unknown word."""
    parts = []
    joined_by_lone_and = False
    i = 0
    while i < len(words):
        word = words[i]
        following = words[i + 1] if i + 1 < len(words) else ""
        i += 1
        if word in _PLACE_WORDS:
            continue
        if word == "و":
            joined_by_lone_and = True
            continue

        if word in _FIRST_OF_TEEN and following in _TEN_WORDS:
            part = ("teen", 10 + _FIRST_OF_TEEN[word], False)
            i += 1
        else:
            part = _look_up(word)
            if part is None:
                return None
            kind, value, joined = part
            if kind == "unit" and value >= 3 and following in _HUNDRED_WORDS:
                part = ("hundred", value * 100, joined)
                i += 1
            elif kind == "unit" and value >= 3 and following in _THOUSAND_WORDS:
                part = ("thousand", value * 1000, joined)
                i += 1
            elif kind in ("unit", "ordinal") and value >= 1 and following in _TEN_WORDS:
                part = ("teen" if kind == "unit" else "ordinal", 10 + value, joined)
                i += 1

        kind, value, joined = part
        parts.append((kind, value, joined or joined_by_lone_and))
        joined_by_lone_and = False
    return parts


def _add_up(group):
    """Step B. Adds the parts of one group. Returns (digits, is_round, size) or None.

    is_round is True for a bare "400" or "1000": the rest of the number may follow
    without "و". size is the smallest part (100 or 1000) so we know what still fits.
    """
    kinds = [kind for kind, _ in group]
    if "digits" in kinds or "ordinal" in kinds:
        return (str(group[0][1]), False, 0) if len(group) == 1 else None
    if len(set(kinds)) != len(kinds):
        return None  # the same kind twice, like "خمسة وستة", is not one number
    if "teen" in kinds and ("unit" in kinds or "tens" in kinds):
        return None
    total = sum(value for _, value in group)
    is_round = all(kind in ("hundred", "thousand") for kind in kinds)
    size = 100 if "hundred" in kinds else 1000
    return (str(total), is_round, size)


def spoken_number(words: str) -> str | None:
    """The digits of a spoken number, or None if the words are not one clear number."""
    parts = _to_parts(normalise(words).split())
    if not parts:
        return None

    # Split into groups: a part that is not joined with "و" starts a new group.
    groups = []
    for kind, value, joined in parts:
        if joined and groups:
            groups[-1].append((kind, value))
        else:
            groups.append([(kind, value)])
    if any(kind == "ordinal" for kind, _, _ in parts) and len(groups) != 1:
        return None  # "the fifth" stands alone

    # Step C: join the groups, left to right.
    result = ""
    last_is_round, last_size, last_digits = False, 0, ""
    for group in groups:
        added = _add_up(group)
        if added is None:
            return None
        digits, is_round, size = added
        if last_is_round and group[0][0] != "digits" and int(digits) < last_size:
            # "تسعمية خمسطعش": the "و" was dropped, so 900 and 15 make 915.
            digits = str(int(last_digits) + int(digits))
            result = result[: -len(last_digits)]
        result += digits
        last_is_round, last_size, last_digits = is_round, size, digits
    return result
