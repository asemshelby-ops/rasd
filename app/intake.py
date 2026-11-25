"""One message comes in and becomes a report in a case. Used by the pages and by the saved scenes.

    report_id, case_id, joined, report = take_in(store, read, text, hotel, photo, source, at)

The order matters: passport and visa numbers are taken out FIRST, so the reader
(the AI model) never sees them. They go to the store's private table only.
"""

from dataclasses import replace
from datetime import datetime

from app.store import Store
from rasd.cases import with_reporting_hotel
from rasd.privacy import redact
from rasd.routing import match_hotel
from rasd.understand import Understanding, understand


def take_in(
    store: Store, read, text: str, hotel: str, photo: bool, source: str, at: datetime
) -> tuple[int, int | None, bool, Understanding]:
    """Reads one message and saves it. read(text, photo_attached) is the engine's reader.

    Returns (report id, case id or None for a message that is not a report,
    whether it joined an existing case, the report).
    """
    safe, private = redact(text)
    if safe.strip():
        report = read(safe, photo_attached=photo)
    else:
        report = understand("", client=None, photo_attached=photo)  # a photo alone: no words to read
    report = replace(report, has_passport_number=bool(private.passport), has_visa_number=bool(private.visa))
    reporting_hotel = match_hotel(hotel)
    report = with_reporting_hotel(report, reporting_hotel)
    report_id, case_id, joined = store.add_report(report, at, reporting_hotel, source, safe, private)
    return report_id, case_id, joined, report
