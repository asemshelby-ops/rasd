"""One message comes in and becomes a report in a case. Used by the pages and by the saved scenes.

    report_id, case_id, joined, report = take_in(store, read, text, hotel, photo, source, at)

The order matters: passport and visa numbers are taken out FIRST, so the reader
(the AI model) never sees them. They go to the store's private table only.

Whatever goes wrong while reading (no key, no network, a fault nobody thought
of), the message is kept and goes to the supervisor. It is never lost.
"""

import logging
from dataclasses import replace
from datetime import datetime

from app.store import Store
from rasd.cases import with_reporting_hotel
from rasd.privacy import redact
from rasd.routing import HOTELS, match_hotel
from rasd.text import language_of
from rasd.understand import Understanding, not_understood, understand

log = logging.getLogger("rasd")

# A longer message is not sent to the model: it would cost and take too long. A person reads it.
MAX_MESSAGE_CHARACTERS = 2000


def listed_hotel(hotel: str) -> str | None:
    """The hotel a sending page says it belongs to, only when it is one of the team's hotels."""
    found = match_hotel(hotel or "")
    return found if found in HOTELS else None


def take_in(
    store: Store, read, text: str, hotel: str, photo: bool, source: str, at: datetime
) -> tuple[int, int | None, bool, Understanding]:
    """Reads one message and saves it. read(text, photo_attached) is the engine's reader.

    Returns (report id, case id or None for a message that is not a report,
    whether it joined an existing case, the report).
    """
    safe, private = redact(text)
    if len(safe) > MAX_MESSAGE_CHARACTERS:
        report = not_understood("the message is too long to read automatically", photo_attached=photo)
        safe = safe[:MAX_MESSAGE_CHARACTERS]
    elif safe.strip():
        try:
            report = read(safe, photo_attached=photo)
        except Exception as e:  # whatever broke, the message is kept and a person reads it
            log.warning("reading failed (%s); the report goes to the supervisor", type(e).__name__)
            report = not_understood(f"the reader failed: {type(e).__name__}", photo_attached=photo)
    else:
        report = understand("", client=None, photo_attached=photo)  # a photo alone: no words to read
    report = replace(report, has_passport_number=bool(private.passport), has_visa_number=bool(private.visa))
    reporting_hotel = listed_hotel(hotel)
    report = with_reporting_hotel(report, reporting_hotel)
    report_id, case_id, joined = store.add_report(report, at, reporting_hotel, source, safe, private, language_of(safe))
    return report_id, case_id, joined, report
