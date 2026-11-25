"""Reads a WhatsApp chat export (the text file, without media) into messages.

Handles what real exports differ in:
  - Android lines ("23/12/2026, 9:41 PM - Name: text") and iPhone lines
    ("[23/12/2026, 21:41:05] Name: text")
  - Western digits and Arabic digits, AM/PM and ص/م, 12-hour and 24-hour time
  - day/month/year, month/day/year and year-month-day dates, 2-digit years,
    and dates in the Hijri calendar
  - messages of several lines, system lines, and media placeholders
"""

import re
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime, time
from pathlib import Path

# Marks WhatsApp puts around right-to-left text. They are invisible and get in the way.
_MARKS = re.compile("[\u200e\u200f\u202a-\u202e\u2066-\u2069\ufeff]")
_SPACES = str.maketrans({"\u202f": " ", "\xa0": " "})
_WESTERN = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")

_DATE = r"(\d{1,4})[/.\-](\d{1,2})[/.\-](\d{1,4})"
_TIME = r"(\d{1,2})[:.](\d{2})(?:[:.](\d{2}))?"
_HALF = r"(?:\s*(?:([AaPp])\.?\s?[Mm]\.?|(ص|م)\S*))?"  # AM / PM, or ص / م
_ANDROID = re.compile(rf"^{_DATE}[,،]?\s+{_TIME}{_HALF}\s+-\s+")
_IPHONE = re.compile(rf"^\[{_DATE}[,،]?\s+{_TIME}{_HALF}\]\s*")

# A message that is only a photo, video, voice note or file. Its content is never read.
_MEDIA = re.compile(
    r"^<[^>]*(omitted|attached|استبعاد|مرفق|محذوف)[^>]*>$"
    r"|^(image|video|audio|sticker|gif|document|contact card) omitted$"
    r"|^.*\(file attached\)$"
    r"|^(صورة|فيديو|مقطع صوتي|ملصق|مستند|صوره) محذوف[ةه]?$"
    r"|^.*\(الملف مرفق\)$",
    re.IGNORECASE,
)
_SYSTEM = ("end-to-end encrypted", "مشفرة تمام", "مشفّرة تمام", "created group", "أنشأ المجموعة", "أنشأت المجموعة")
_DELETED = ("this message was deleted", "you deleted this message", "تم حذف هذه الرسالة", "حذفت هذه الرسالة")


@dataclass
class Message:
    at: datetime
    sender: str  # used for nothing and never printed
    text: str  # "" for a photo or other media with no caption
    media: bool = False


@dataclass
class Parsed:
    messages: list[Message]
    notes: list[str] = field(default_factory=list)  # "date_order_assumed", "hijri_dates"


def read_export(path: Path) -> str:
    """The text of an export. A .zip (as iPhones make) is opened and its chat text is read."""
    path = Path(path)
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            texts = [name for name in archive.namelist() if name.lower().endswith(".txt")]
            if not texts:
                return ""
            return archive.read(texts[0]).decode("utf-8-sig", errors="replace")
    return path.read_text(encoding="utf-8-sig", errors="replace")


def _hijri_to_date(year: int, month: int, day: int) -> date:
    """A date of the Hijri calendar as a day of the usual calendar (tabular rule).

    The real calendar follows the moon and can differ by a day. Distances
    between messages stay right except, at most by one day, across a month's end.
    """
    if not (1 <= month <= 12 and 1 <= day <= 30):
        raise ValueError("not a Hijri date")
    julian_day = (11 * year + 3) // 30 + 354 * year + 30 * month - (month - 1) // 2 + day + 1948440 - 385
    return date.fromordinal(julian_day - 1721425)


def _headers(lines: list[str]):
    """Each line with its header match (or None). Digits are read in either style."""
    for line in lines:
        western = line.translate(_WESTERN)
        yield line, _ANDROID.match(western) or _IPHONE.match(western)


def parse_export(text: str, month_first: bool | None = None) -> Parsed:
    """The messages of an export, oldest first as written.

    month_first: True for month/day/year dates, False for day/month/year. When
    it is not given, the dates themselves decide; if they cannot (no day above
    12 anywhere), day first is assumed and a note says so.
    """
    lines = [_MARKS.sub("", line).translate(_SPACES) for line in text.splitlines()]
    matches = list(_headers(lines))
    triples = [tuple(int(part) for part in match.groups()[:3]) for _, match in matches if match]
    notes = []
    year_first = any(a > 31 for a, _, _ in triples)
    if month_first is None and not year_first:
        if any(a > 12 for a, _, _ in triples):
            month_first = False
        elif any(b > 12 for _, b, _ in triples):
            month_first = True
        else:
            month_first = False
            if triples:
                notes.append("date_order_assumed")

    def when(match) -> datetime | None:
        a, b, c, hour, minute, second, latin_half, arabic_half = match.groups()
        a, b, c = int(a), int(b), int(c)
        year, month, day = (a, b, c) if year_first else ((c, a, b) if month_first else (c, b, a))
        if year < 100:
            year += 2000
        hour = int(hour)
        half = (latin_half or "").lower() or {"ص": "a", "م": "p"}.get(arabic_half or "", "")
        if half == "p" and hour < 12:
            hour += 12
        if half == "a" and hour == 12:
            hour = 0
        try:
            if 1300 <= year <= 1600:
                if "hijri_dates" not in notes:
                    notes.append("hijri_dates")
                day_of = _hijri_to_date(year, month, day)
            else:
                day_of = date(year, month, day)
            return datetime.combine(day_of, time(hour, int(minute), int(second or 0)))
        except ValueError:
            return None

    messages: list[Message] = []
    current: Message | None = None
    for line, match in matches:
        at = when(match) if match else None
        if at is None:
            if current is not None:  # a further line of the message above
                current.text = f"{current.text}\n{line}" if current.text else line
            continue
        current = None
        rest = line[match.end() :]
        if ": " not in rest and not rest.endswith(":"):
            continue  # a system line: someone joined, the group was renamed
        sender, _, body = rest.partition(": ")
        body = body.strip()
        if any(phrase in body.lower() for phrase in _SYSTEM):
            continue
        media = bool(_MEDIA.match(body))
        if media or any(phrase in body.lower() for phrase in _DELETED):
            body = ""
        current = Message(at=at, sender=sender.strip(), text=body, media=media)
        messages.append(current)
    for message in messages:
        message.text = message.text.strip()
    return Parsed(messages, notes)
