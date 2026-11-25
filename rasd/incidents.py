"""Duplicate merging: several messages about the same problem become one incident.

    incidents = group_reports([(report_id, sent_at, report), ...])

The rule (no AI in here):
  - same type + same place + sent within MERGE_WINDOW_MINUTES of the incident's
    latest message  ->  the message joins that incident
  - anything else starts a new incident

A report never merges when we are not sure what it is or where it is:
  - its type is unclear
  - its place has no number (no location, a room without its number, or a
    common area: we do not know which one)
  - it is waiting for the supervisor to confirm it (for example its room number
    was not confirmed, or the model was not confident)
Such a report is always an incident of its own. A wrong merge would hide a
pilgrim's problem inside another incident; a missed merge only shows one card
too many on the board.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from rasd.schema import URGENCIES
from rasd.understand import Understanding

# How long after the latest message of an incident a new message about the same
# problem still counts as the same incident. This is a first judgement, not a
# measured value: the team may change it.
MERGE_WINDOW_MINUTES = 60

_MOST_URGENT_FIRST = list(URGENCIES)


@dataclass
class Incident:
    type: str  # a code from schema.TYPES
    loc_kind: str  # a code from schema.LOCATION_KINDS
    loc_number: str | None
    urgency: str  # the most urgent of its messages
    report_ids: list[int]  # in the order the messages were sent
    first_at: datetime
    last_at: datetime

    @property
    def message_count(self) -> int:
        return len(self.report_ids)


def can_merge(report: Understanding) -> bool:
    """True when we are sure enough of the type and the place to merge this report."""
    return report.type != "unclear" and report.loc_number is not None and not report.needs_confirmation


def group_reports(arrivals, window_minutes: int = MERGE_WINDOW_MINUTES) -> list[Incident]:
    """Groups reports into incidents. arrivals is a list of (report id, time sent, report)."""
    window = timedelta(minutes=window_minutes)
    incidents = []
    growing = {}  # (type, place kind, place number) -> the latest incident a new message may join
    for report_id, sent_at, report in sorted(arrivals, key=lambda arrival: arrival[1]):
        key = (report.type, report.loc_kind, report.loc_number)
        incident = growing.get(key) if can_merge(report) else None
        if incident is not None and sent_at - incident.last_at <= window:
            incident.report_ids.append(report_id)
            incident.last_at = sent_at
            incident.urgency = min(incident.urgency, report.urgency, key=_MOST_URGENT_FIRST.index)
            continue
        incident = Incident(
            type=report.type,
            loc_kind=report.loc_kind,
            loc_number=report.loc_number,
            urgency=report.urgency,
            report_ids=[report_id],
            first_at=sent_at,
            last_at=sent_at,
        )
        incidents.append(incident)
        if can_merge(report):
            growing[key] = incident
    return incidents
