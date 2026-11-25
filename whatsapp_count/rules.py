"""Plain keyword and pattern rules. No AI model.

    looks_like_report(text)     the message reports a problem
    names_hotel(text, hotels)   it says which hotel
    names_room(text)            it says which room, with its number
    looks_like_closure(text)    a reply such as "لقيناها", "تم" or a thumbs-up

The word lists are at the top so that the team can change them. They are a
rough net: the hand-check mode measures how often they agree with a person.
"""

import re

# One spelling per letter, so that a keyword is written here only once.
_MARKS = re.compile("[ً-ٰٟـ‎‏]")  # vowel marks, the stretching line
_SAME_LETTER = str.maketrans(
    {
        "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ة": "ه", "ؤ": "و", "ئ": "ي",
        "ک": "ك", "ی": "ي", "ے": "ي", "ہ": "ه", "ھ": "ه", "ۃ": "ه",
    }  # fmt: skip
)
_WESTERN = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def normalise(text: str) -> str:
    return _MARKS.sub("", text).translate(_SAME_LETTER).translate(_WESTERN).lower()


# Short words Arabic glues to the front of a word (و ف ب ل ك), and the article.
_FRONT = r"(?<![\w])(?:[وفبلك]{0,2})(?:ال|ل)?"

# A message looks like a report when it has a STRONG word, or a TOPIC word together with a CUE.
#   STRONG  the word itself says something is wrong: "خربان", "ضاع", "مريض"
#   TOPIC   what reports are about: "مكيف", "شنط", "وجبات". Alone it proves nothing ("تم توزيع الوجبات")
#   CUE     something is missing or needed: "ما", "مافي", "يحتاج", "وين"
# A stem matches a word that STARTS with it (after glued letters); a word must match whole.
STRONG_STEMS = [
    "ضاع", "ضيع", "ضايع", "ضائع", "مفقود", "تايه", "تائه", "تاه", "تهت",
    "مريض", "تعبان", "مغمي", "اغمي", "اسعاف", "دايخ", "ينزف", "نزيف",
    "خربان", "عطلان", "معطل", "متعطل", "تعطل", "مقطوع", "انقطع", "انقطاع", "طافي", "مكسور", "تسريب", "تسرب", "يسرب",
    "ساعدو", "مساعده", "شكوي", "يشتكي", "تشتكي",
    "بيمار",
]  # fmt: skip
STRONG_WORDS = ["عطل", "خراب", "گم", "مدد", "lost", "missing", "broken", "leak", "leaking", "sick"]
STRONG_PHRASES = ["not working", "no water", "does not work", "doesn't work"]

TOPIC_STEMS = [
    "مكيف", "تكييف", "موي", "مياه", "كهرب", "مصعد", "اصنصير", "اسانسير", "لمبه", "لمبات",
    "شنط", "عفش", "امتعه", "حقيب", "حقايب", "نظافه", "تنظيف", "هديه", "هدايا", "وجبه", "وجبات", "نسك", "بطاقه", "بطاقت",
    "دواء", "ادويه", "دكتور", "طبيب", "سامان",
]  # fmt: skip
TOPIC_WORDS = ["ماء", "دوا", "دواه", "پاني", "لفٹ", "ac", "water", "luggage", "bag", "bags", "card"]

CUE_WORDS = [
    "ما", "مافي", "مافيه", "مو", "مش", "بدون", "ناقص", "ناقصه", "وين", "فين", "لسا", "للحين",
    "يحتاج", "تحتاج", "نحتاج", "محتاج", "محتاجه", "يبغي", "تبغي", "نبغي", "ابغي", "يبي", "نبي",
    "نہيں", "نهيں", "چاہيي", "no", "not", "need", "needs",
]  # fmt: skip
CUE_STEMS = ["تاخر", "متاخر"]


def _any(stems=(), words=(), phrases=()) -> re.Pattern:
    parts = []
    if stems:
        parts.append(_FRONT + "(?:" + "|".join(re.escape(normalise(stem)) for stem in stems) + ")")
    if words:
        parts.append(_FRONT + "(?:" + "|".join(re.escape(normalise(word)) for word in words) + r")(?![\w])")
    parts += [re.escape(normalise(phrase)) for phrase in phrases]
    return re.compile("|".join(parts))


_STRONG = _any(STRONG_STEMS, STRONG_WORDS, STRONG_PHRASES)
_TOPIC = _any(TOPIC_STEMS, TOPIC_WORDS)
_CUE = _any(CUE_STEMS, CUE_WORDS)

# Words that say "this is a hotel".
HOTEL_WORDS = ["فندق", "برج", "ابراج", "اوتيل", "هوتيل", "hotel", "ہوٹل"]
_HOTEL = re.compile(_FRONT + "(?:" + "|".join(re.escape(normalise(word)) for word in HOTEL_WORDS) + ")")

# A room with its number: "غرفة 318", "الغرفة رقم 318", "room 204", or the number in words.
_NUMBER_WORD = r"(?:مي[هت]|ميت|مئ|ثلاثمي|ثلثمي|اربعمي|خمسمي|ستمي|سبعمي|ثمانمي|ثمنمي|تسعمي|الف|واحد|اثنين|ثنتين|ثلاث|اربع|خمس|ست|سبع|ثمان|تسع|عشر)"
_ROOM = re.compile(
    _FRONT + r"(?:غرف[هت]|روم|جناح|كمر[هي])\s*(?:رقم|نمبر)?\s*[:#]?\s*(?:\d{1,5}(?!\d)|" + _NUMBER_WORD + ")"
    + r"|(?<![\w])(?:room|suite)\s*(?:no\.?|number|#)?\s*\d{1,5}(?!\d)"
)  # fmt: skip

# A closing reply is short and says it is done or found.
CLOSURE_STEMS = ["لقيناه", "لقيته", "لقيتها", "لقوه", "لقوها", "وجدناه", "وجدته", "انحل", "اتحل", "تصلح", "اتصلح", "صلحناه", "صلحوه"]
CLOSURE_WORDS = ["تم", "تمت", "خلاص", "done", "fixed", "found", "solved", "resolved"]
CLOSURE_PHRASES = ["مل گيا", "ہو گيا", "ٹھيك ہو"]
CLOSURE_SIGNS = ["👍", "✅", "👌", "✔"]
CLOSURE_MAX_WORDS = 6

_CLOSURE = _any(CLOSURE_STEMS, CLOSURE_WORDS, CLOSURE_PHRASES)


def looks_like_report(text: str) -> bool:
    """True when the message seems to report a problem."""
    clean = normalise(text)
    return bool(_STRONG.search(clean)) or bool(_TOPIC.search(clean) and _CUE.search(clean))


def looks_like_closure(text: str) -> bool:
    """True for a short reply that says a problem is over. It closes nothing in Rasd: it is only counted."""
    clean = normalise(text)
    if not clean.strip() or len(clean.split()) > CLOSURE_MAX_WORDS or looks_like_report(text):
        return False
    return bool(_CLOSURE.search(clean)) or any(sign in text for sign in CLOSURE_SIGNS)


def names_hotel(text: str, hotels=()) -> bool:
    """True when the message says which hotel. hotels: the team's own hotel names, if they give a list."""
    clean = normalise(text)
    return bool(_HOTEL.search(clean)) or any(normalise(name).strip() in clean for name in hotels if name.strip())


def names_room(text: str) -> bool:
    """True when the message gives a room with its number."""
    return bool(_ROOM.search(normalise(text)))
