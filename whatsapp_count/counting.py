"""Turns the messages of a group into counts. Aggregates only.

A closing reply ("لقيناها", "تم", a thumbs-up) is given to the latest report
before it that has no closing reply yet. An export does not say which message
a reply answers, so this is the nearest fair guess.
"""

import statistics
from dataclasses import dataclass, field
from datetime import timedelta

from whatsapp_count.rules import looks_like_closure, looks_like_report, names_hotel, names_room

NOTES = {
    "date_order_assumed": "ترتيب اليوم والشهر في التواريخ غير محسوم من الملف، فافتُرض أن اليوم أولاً. إن كان الشهر أولاً فأعيدوا التشغيل مع ‎--month-first",
    "hijri_dates": "التواريخ هجرية، فالمدد عبر نهاية شهر قد تختلف يوماً واحداً.",
}


@dataclass
class Counts:
    messages: int = 0
    media_messages: int = 0
    days: int = 0
    reports: int = 0
    missing_hotel: int = 0
    missing_room: int = 0
    missing_either: int = 0
    no_closure: int = 0
    closure_minutes: list[float] = field(default_factory=list)  # one per report that got a closing reply
    window_hours: int = 24

    @property
    def median_minutes(self) -> float | None:
        return statistics.median(self.closure_minutes) if self.closure_minutes else None


def count(messages, hotels=(), window_hours: int = 24) -> Counts:
    """Counts the group. hotels: the team's own hotel names (optional)."""
    counts = Counts(window_hours=window_hours)
    counts.messages = len(messages)
    counts.media_messages = sum(1 for message in messages if message.media and not message.text)
    counts.days = len({message.at.date() for message in messages})
    window = timedelta(hours=window_hours)
    open_reports = []  # [time, minutes until its closing reply or None]
    all_reports = []
    for message in sorted(messages, key=lambda m: m.at):
        if looks_like_report(message.text):
            hotel, room = names_hotel(message.text, hotels), names_room(message.text)
            counts.reports += 1
            counts.missing_hotel += not hotel
            counts.missing_room += not room
            counts.missing_either += not (hotel and room)
            report = [message.at, None]
            open_reports.append(report)
            all_reports.append(report)
        elif looks_like_closure(message.text):
            while open_reports:
                report = open_reports.pop()  # the latest report that is still open
                if message.at - report[0] <= window:
                    report[1] = (message.at - report[0]).total_seconds() / 60
                    break
    counts.closure_minutes = [report[1] for report in all_reports if report[1] is not None]
    counts.no_closure = counts.reports - len(counts.closure_minutes)
    return counts


def _share(part: int, whole: int) -> str:
    return f"{part} من {whole} ({round(100 * part / whole)}%)" if whole else "0"


def _duration(minutes: float) -> str:
    if minutes < 120:
        return f"{minutes:g} دقيقة" if minutes == round(minutes, 1) else f"{minutes:.1f} دقيقة"
    return f"{minutes / 60:.1f} ساعة"


def render(counts: Counts, notes=()) -> str:
    """The report, in Arabic. It holds counts and shares only: no name, no number, no text."""
    lines = [
        "عدّ رسائل مجموعة واتساب: أرقام مجمّعة فقط",
        "",
        f"عدد الرسائل: {counts.messages}",
        f"  منها وسائط بلا نص (لم تُقرأ): {counts.media_messages}",
        f"عدد الأيام التي فيها رسائل: {counts.days}",
        f"رسائل تشبه البلاغات: {_share(counts.reports, counts.messages)}",
        f"بلاغات لم تذكر الفندق: {_share(counts.missing_hotel, counts.reports)}",
        f"بلاغات لم تذكر الغرفة برقمها: {_share(counts.missing_room, counts.reports)}",
        f"بلاغات ينقصها الفندق أو الغرفة: {_share(counts.missing_either, counts.reports)}",
        f"بلاغات بلا رد إغلاق ظاهر خلال {counts.window_hours} ساعة: {_share(counts.no_closure, counts.reports)}",
    ]
    if counts.median_minutes is None:
        lines.append("وسيط الزمن حتى رد الإغلاق: لا يوجد، فلا بلاغ له رد إغلاق")
    else:
        lines.append(
            f"وسيط الزمن حتى رد الإغلاق: {_duration(counts.median_minutes)} (من {len(counts.closure_minutes)} بلاغات لها رد)"
        )
    lines += [
        "",
        "كيف حُسبت: بقواعد كلمات وأنماط على هذا الحاسوب، بلا إنترنت وبلا نموذج ذكاء اصطناعي.",
        "رد الإغلاق (مثل «لقيناها» أو «تم» أو 👍) يُنسب إلى أقرب بلاغ قبله لم يُغلق.",
        "هذه تقديرات. وضع المراجعة اليدوية يقيس كم توافق القواعد حكمكم.",
    ]
    lines += [f"ملاحظة: {NOTES[note]}" for note in notes if note in NOTES]
    return "\n".join(lines)
