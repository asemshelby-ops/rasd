"""Loads the test reports and the table of expected answers from the data folder.

Conventions in expected.csv:
  - an empty cell means "do not score this field for this report"
  - "-" in loc_number means "no number is expected"
"""

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from rasd.schema import LOCATION_KINDS, OWNERS, TYPES, URGENCIES

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
NO_NUMBER = "-"


@dataclass(frozen=True)
class SampleReport:
    id: int
    sent_at: datetime
    lang: str  # ar-sa, ar-ps or ur
    text: str


@dataclass(frozen=True)
class Expected:
    id: int
    type: str
    loc_kind: str | None  # None = location not scored
    loc_number: str | None  # "-" = no number expected
    urgency: str | None  # None = not scored
    owner: str
    incident: int
    needs_confirmation: bool | None  # None = not scored
    room_in_words: bool
    note: str


def _read_rows(path: Path) -> list[dict]:
    try:
        with open(path, encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))
    except UnicodeDecodeError:
        raise ValueError(
            f"{path.name} is not saved as UTF-8. In Excel choose "
            "'CSV UTF-8 (Comma delimited)' when saving."
        ) from None


def _check(value: str, allowed, column: str, report_id: str) -> str:
    if value not in allowed:
        raise ValueError(
            f"expected.csv, report {report_id}: '{value}' is not a valid {column}. "
            f"Allowed: {', '.join(allowed)}"
        )
    return value


def load_reports(path: Path = DATA_DIR / "reports.csv") -> list[SampleReport]:
    return [
        SampleReport(
            id=int(row["id"]),
            sent_at=datetime.strptime(row["sent_at"], "%Y-%m-%d %H:%M"),
            lang=row["lang"],
            text=row["text"],
        )
        for row in _read_rows(path)
    ]


def load_expected(path: Path = DATA_DIR / "expected.csv") -> dict[int, Expected]:
    expected = {}
    for row in _read_rows(path):
        rid = row["id"]
        kind = row["loc_kind"] or None
        flag = row["needs_confirmation"]
        expected[int(rid)] = Expected(
            id=int(rid),
            type=_check(row["type"], TYPES, "type", rid),
            loc_kind=_check(kind, LOCATION_KINDS, "loc_kind", rid) if kind else None,
            loc_number=row["loc_number"] if kind else None,
            urgency=_check(row["urgency"], URGENCIES, "urgency", rid) if row["urgency"] else None,
            owner=_check(row["owner"], OWNERS, "owner", rid),
            incident=int(row["incident"]),
            needs_confirmation=(flag == "1") if flag else None,
            room_in_words=row["room_in_words"] == "1",
            note=row["note"],
        )
    return expected
