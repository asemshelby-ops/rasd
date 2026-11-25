"""Rules that belong to a case as the board shows it, on top of the reading of one message.

    report = with_reporting_hotel(report, "برج السكينة")     the counter the message came from
    request = replacement_request(report, reported_at)      a lost Nusuk card starts a 24-hour clock

No AI in here.
"""

from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from rasd.routing import CHECKLISTS
from rasd.understand import Understanding, settle

# A replacement for a lost or damaged Nusuk card is followed for this many hours.
REPLACEMENT_HOURS = 24


def with_reporting_hotel(report: Understanding, reporting_hotel: str | None, stage: str | None = None) -> Understanding:
    """Gives a report the hotel it was sent from, when its message names no hotel.

    A counter's reporting page belongs to one hotel, so a message from it is
    about that hotel unless it says otherwise.
    """
    hotel = (reporting_hotel or "").strip()
    if not hotel or report.hotel or not report.is_report:
        return report
    return settle(replace(report, hotel=hotel), stage)


@dataclass(frozen=True)
class ReplacementRequest:
    """A request to replace a Nusuk card, filled in from a complete report."""

    pilgrim_name: str | None  # never shown in full on the big screen
    hotel: str | None
    room: str | None
    has_passport_number: bool
    has_visa_number: bool
    reported_at: datetime
    due_at: datetime  # reported_at + REPLACEMENT_HOURS
    missing: tuple[str, ...]  # the checklist items the report did not give


def replacement_request(report: Understanding, reported_at: datetime) -> ReplacementRequest | None:
    """The replacement request a lost or damaged card report starts, or None.

    Only a complete report starts one: a report that still needs the
    supervisor or the sender's answer does not.
    """
    if report.type != "nusuk_card" or report.needs_confirmation:
        return None
    known = {
        "الاسم الكامل كما في الجواز": bool(report.pilgrim_name),
        "رقم التأشيرة": report.has_visa_number,
        "رقم الجواز": report.has_passport_number,
        "الشركة والفندق والغرفة": bool(report.hotel) and report.loc_number is not None,
    }
    return ReplacementRequest(
        pilgrim_name=report.pilgrim_name,
        hotel=report.hotel,
        room=report.loc_number if report.loc_kind == "room" else None,
        has_passport_number=report.has_passport_number,
        has_visa_number=report.has_visa_number,
        reported_at=reported_at,
        due_at=reported_at + timedelta(hours=REPLACEMENT_HOURS),
        missing=tuple(item for item in CHECKLISTS["nusuk_card"] if not known.get(item, False)),
    )
