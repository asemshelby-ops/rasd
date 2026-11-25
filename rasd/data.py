"""Loads the test reports and the tables of expected answers.

There are two sets of reports, in exactly the same format:
  data/reports.csv + data/expected.csv           the 35 reports written with the AI assistant
  data/holdout/reports.csv + expected.csv        the owner's own reports (empty until they are written)

Conventions in expected.csv:
  - an empty cell means "do not score this field for this report"
  - "-" in loc_number means "no number is expected"
  - urgency is the priority level; it is written for the journey stage EXPECTED_STAGE
  - risks (an optional column) lists the risks the message states, separated by spaces
  - partial (an optional column) is 1 when the message says the fault is only partial
  - hotel, name and ask (optional columns): the hotel's name, the pilgrim's name, and
    the field Rasd should ask the sender about; "-" means "none"
In reports.csv the optional column photo is 1 when a photo came with the message;
such a message may have no words.

A mistake in a file stops the program with a message that names the file, the
report number and the column. The messages never show the words of a report or
the content of a cell, so the holdout reports stay unseen.
"""

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from rasd.schema import LOCATION_KINDS, OWNERS, RISKS, TYPES, URGENCIES
from rasd.text import to_western_digits

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
HOLDOUT_DIR = DATA_DIR / "holdout"
NO_NUMBER = "-"  # in loc_number, hotel, name and ask: "none is expected"
ASK_FIELDS = ("type", "place", "hotel", "name")  # what Rasd may ask the sender about

# The stage of the journey that the expected priorities are written for. The
# benchmark always scores with this stage, whatever routing.CURRENT_STAGE says.
EXPECTED_STAGE = "makkah"

REPORT_COLUMNS = ("id", "sent_at", "lang", "text")
EXPECTED_COLUMNS = (
    "id", "type", "loc_kind", "loc_number", "urgency", "owner", "incident", "needs_confirmation", "room_in_words",
)  # fmt: skip
TIME_FORMATS = ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S")


@dataclass(frozen=True)
class SampleReport:
    id: int
    sent_at: datetime
    lang: str  # ar-sa, ar-ps or ur
    text: str  # may be empty when a photo came alone
    photo: bool = False  # True when a photo came with the message


@dataclass(frozen=True)
class Expected:
    id: int
    type: str
    loc_kind: str | None  # None = location not scored
    loc_number: str | None  # "-" = no number expected
    urgency: str | None  # None = not scored
    owner: str
    incident: int | None  # None = grouping is not scored
    needs_confirmation: bool | None  # None = not scored
    room_in_words: bool
    note: str
    risks: tuple[str, ...] | None = None  # the risks the message states; None = the file has no risks column
    partial: bool = False  # True when the message says the fault is only partial
    hotel: str | None = None  # None = not scored; "-" = the message names no hotel
    name: str | None = None  # the pilgrim's name; None = not scored; "-" = no name
    ask: str | None = None  # a code from ASK_FIELDS; None = not scored; "-" = no question


def _name(path: Path) -> str:
    """A short name for a file in error messages, for example 'holdout/expected.csv'."""
    return f"{path.parent.name}/{path.name}"


def _read_rows(path: Path, columns) -> list[tuple[int, dict]]:
    """The rows of a CSV file as (row number in the file, cells). Blank rows are skipped."""
    try:
        with open(path, encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            rows = [{key: (value or "").strip() for key, value in row.items() if key} for row in reader]
            header = reader.fieldnames or []
    except UnicodeDecodeError:
        raise ValueError(
            f"{_name(path)} is not saved as UTF-8. In Excel choose 'CSV UTF-8 (Comma delimited)' when saving."
        ) from None
    missing = [column for column in columns if column not in header]
    if missing:
        raise ValueError(
            f"{_name(path)}: the column {', '.join(missing)} is missing. "
            f"The first row of the file must be: {','.join(columns)}"
        )
    return [(number, row) for number, row in enumerate(rows, start=2) if any(row.values())]


def _report_id(row: dict, file: str, row_number: int, seen: set) -> int:
    if not row["id"].isdigit():
        raise ValueError(f"{file}, row {row_number}: the id must be a whole number such as 7.")
    report_id = int(row["id"])
    if report_id in seen:
        raise ValueError(f"{file}: the report number {report_id} is used more than once.")
    seen.add(report_id)
    return report_id


def _code(value: str, allowed, column: str, where: str) -> str:
    if value not in allowed:
        raise ValueError(f"{where}: the {column} is not valid. Allowed: {', '.join(allowed)}")
    return value


def _yes_no(value: str, column: str, where: str) -> bool | None:
    """1 -> True, 0 -> False, empty -> None."""
    if value not in ("", "0", "1"):
        raise ValueError(f"{where}: the {column} must be 1, 0 or empty.")
    return (value == "1") if value else None


def _time(value: str, where: str) -> datetime:
    for time_format in TIME_FORMATS:
        try:
            return datetime.strptime(value, time_format)
        except ValueError:
            pass
    raise ValueError(
        f"{where}: the sent_at time must look like 2026-12-22 08:02. "
        "Excel may have rewritten it: format that column as Text before typing."
    )


def load_reports(path: Path = DATA_DIR / "reports.csv") -> list[SampleReport]:
    file, seen, reports = _name(path), set(), []
    for row_number, row in _read_rows(path, REPORT_COLUMNS):
        report_id = _report_id(row, file, row_number, seen)
        where = f"{file}, report {report_id}"
        if not (row["lang"].startswith("ar") or row["lang"] == "ur"):
            raise ValueError(f"{where}: the lang must be ar-sa, ar-ps or ur.")
        photo = bool(_yes_no(row.get("photo", ""), "photo", where))
        if not row["text"] and not photo:
            raise ValueError(f"{where}: the text is empty.")
        reports.append(
            SampleReport(
                id=report_id, sent_at=_time(row["sent_at"], where), lang=row["lang"], text=row["text"], photo=photo
            )
        )
    return reports


def load_expected(path: Path = DATA_DIR / "expected.csv") -> dict[int, Expected]:
    file, seen, expected = _name(path), set(), {}
    for row_number, row in _read_rows(path, EXPECTED_COLUMNS):
        report_id = _report_id(row, file, row_number, seen)
        where = f"{file}, report {report_id}"

        kind = _code(row["loc_kind"], LOCATION_KINDS, "loc_kind", where) if row["loc_kind"] else None
        number = to_western_digits(row["loc_number"]) if kind else None
        if kind and not (number == NO_NUMBER or number.isdigit()):
            raise ValueError(f"{where}: the loc_number must be digits, or {NO_NUMBER} when no number is expected.")
        if row["incident"] and not row["incident"].isdigit():
            raise ValueError(f"{where}: the incident must be a whole number, or empty.")
        ask = row.get("ask") or None
        if ask not in (None, NO_NUMBER, *ASK_FIELDS):
            raise ValueError(f"{where}: the ask is not valid. Allowed: {', '.join(ASK_FIELDS)}, or {NO_NUMBER}")
        risks = tuple(row["risks"].split()) if "risks" in row else None
        if risks and not set(risks) <= set(RISKS):
            raise ValueError(f"{where}: the risks are not valid. Allowed, separated by spaces: {', '.join(RISKS)}")

        expected[report_id] = Expected(
            id=report_id,
            type=_code(row["type"], TYPES, "type", where),
            loc_kind=kind,
            loc_number=number,
            urgency=_code(row["urgency"], URGENCIES, "urgency", where) if row["urgency"] else None,
            owner=_code(row["owner"], OWNERS, "owner", where),
            incident=int(row["incident"]) if row["incident"] else None,
            needs_confirmation=_yes_no(row["needs_confirmation"], "needs_confirmation", where),
            room_in_words=bool(_yes_no(row["room_in_words"], "room_in_words", where)),
            note=row.get("note", ""),
            risks=risks,
            partial=bool(_yes_no(row.get("partial", ""), "partial", where)),
            hotel=row.get("hotel") or None,
            name=row.get("name") or None,
            ask=ask,
        )
    return expected


def load_holdout(folder: Path = HOLDOUT_DIR) -> tuple[list[SampleReport], dict[int, Expected]] | None:
    """The owner's own reports and their expected answers, or None when there are none yet."""
    reports_file, expected_file = folder / "reports.csv", folder / "expected.csv"
    if not reports_file.exists():
        return None
    reports = load_reports(reports_file)
    if not reports:
        return None
    if not expected_file.exists():
        raise ValueError(f"{_name(reports_file)} has reports, but {_name(expected_file)} does not exist.")
    expected = load_expected(expected_file)

    report_ids, answer_ids = {r.id for r in reports}, set(expected)
    if report_ids != answer_ids:
        raise ValueError(
            f"{folder.name}: reports.csv and expected.csv must list the same report numbers. "
            f"Only in reports.csv: {sorted(report_ids - answer_ids)}. "
            f"Only in expected.csv: {sorted(answer_ids - report_ids)}."
        )
    return reports, expected
