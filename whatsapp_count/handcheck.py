"""Hand check: the owner marks a random sample, and the tool says how often its rules agree.

    write_sample(messages, path)    writes 50 random messages to a local file
    score(messages, path)           reads the marks back and compares

The file holds message text, because the owner has to read a message to judge
it. It holds no sender name, and long numbers (phones, passports) are masked.
It must stay on the laptop: the command refuses to write it inside the repository.
"""

import csv
import hashlib
import random
import re
from dataclasses import dataclass
from pathlib import Path

from whatsapp_count.rules import looks_like_report

COLUMNS = ["id", "text", "report", "check"]
_LONG_NUMBER = re.compile(r"[0-9٠-٩۰-۹]{7,}")
YES = {"y", "yes", "1", "نعم", "ن", "بلاغ", "صح"}
NO = {"n", "no", "0", "لا", "ل", "خطأ", "خطا"}


def _fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def write_sample(messages, path: Path, size: int = 50, seed: int | None = None) -> int:
    """Writes up to `size` random messages that have text. Returns how many were written."""
    with_text = [index for index, message in enumerate(messages) if message.text.strip()]
    chosen = sorted(random.Random(seed).sample(with_text, min(size, len(with_text))))
    with Path(path).open("w", encoding="utf-8-sig", newline="") as file:  # utf-8-sig: Excel shows Arabic correctly
        writer = csv.DictWriter(file, fieldnames=COLUMNS)
        writer.writeheader()
        for index in chosen:
            text = _LONG_NUMBER.sub("[رقم]", messages[index].text).replace("\n", " / ")
            writer.writerow({"id": index, "text": text, "report": "", "check": _fingerprint(messages[index].text)})
    return len(chosen)


@dataclass
class Agreement:
    marked: int = 0
    agree: int = 0
    owner_yes_tool_no: int = 0
    owner_no_tool_yes: int = 0
    unmarked: int = 0

    @property
    def rate(self) -> float | None:
        return self.agree / self.marked if self.marked else None


def score(messages, path: Path) -> Agreement:
    """Compares the owner's marks with the rules. Raises ValueError when the file does not fit the export."""
    result = Agreement()
    with Path(path).open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    for number, row in enumerate(rows, start=2):  # row 1 is the heading
        try:
            index = int(row["id"])
            message = messages[index]
        except (KeyError, ValueError, IndexError, TypeError):
            raise ValueError("this hand-check file does not belong to this export") from None
        if index < 0 or _fingerprint(message.text) != (row.get("check") or "").strip():
            raise ValueError("this hand-check file does not belong to this export")
        mark = (row.get("report") or "").strip().lower()
        if not mark:
            result.unmarked += 1
            continue
        if mark not in YES | NO:
            raise ValueError(f"row {number}: write y or n in the 'report' column")
        owner, tool = mark in YES, looks_like_report(message.text)
        result.marked += 1
        result.agree += owner == tool
        result.owner_yes_tool_no += owner and not tool
        result.owner_no_tool_yes += tool and not owner
    return result


def render_agreement(result: Agreement) -> str:
    """The agreement, in Arabic. Counts only."""
    if not result.marked:
        return "لم تُعلَّم أي رسالة بعد. اكتبوا y أو n في عمود report ثم أعيدوا التشغيل."
    lines = [
        "المراجعة اليدوية: توافق القواعد مع حكمكم",
        "",
        f"رسائل علّمتموها: {result.marked}",
        f"توافقت القواعد معكم في: {result.agree} من {result.marked} ({round(100 * result.rate)}%)",
        f"قلتم بلاغ والقواعد لم تلتقطه: {result.owner_yes_tool_no}",
        f"قلتم ليس بلاغاً والقواعد التقطته: {result.owner_no_tool_yes}",
    ]
    if result.unmarked:
        lines.append(f"رسائل تُركت بلا علامة ولم تُحسب: {result.unmarked}")
    return "\n".join(lines)
