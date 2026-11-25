"""Duplicate merging: several messages about the same problem become one incident.

    incident = add_report(incidents, report_id, sent_at, report)     one new report (the live system)
    incidents = group_reports([(report_id, sent_at, report), ...])   a whole list at once (the benchmark)

The rule (no AI in here):
  - same type + same place + sent within MERGE_WINDOW_MINUTES of the incident's
    latest message  ->  the message joins that incident
  - anything else starts a new incident
The place is the hotel together with the room, floor or elevator number.

A lost pilgrim has no room, so that type has its own rule: two reports of a lost
pilgrim from the same hotel within LOST_PILGRIM_WINDOW_MINUTES are one case, for
example the counter employee's message and the pilgrim's own voice note.

A message that is not a report (attendance, chat, a reply) makes no incident.

Closing: an incident is closed only by close_incident(), which records when and
by whom. No chat message closes anything, whatever it says ("found it", a
thumbs-up): a message can only become a report, or nothing.

A closed incident takes no more reports. A new report about the same problem in
the same place opens a new incident, even inside the window: the problem came back.

A report never merges when we are not sure what it is or where it is:
  - its type is unclear
  - its place has no number (no location, a room without its number, or a
    common area: we do not know which one)
  - it is waiting for the supervisor to confirm it (for example its room number
    was not confirmed, or the model was not confident)
Such a report is always an incident of its own, and nothing joins it. A wrong
merge would hide a pilgrim's problem inside another incident; a missed merge
only shows one card too many on the board.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from rasd.schema import URGENCIES
from rasd.understand import Understanding

# How long after the latest message of an incident a new message about the same
# problem still counts as the same incident. This is the team's judgement, not a
# measured value: change it here.
MERGE_WINDOW_MINUTES = 60

# Two reports of a lost pilgrim from the same hotel within this many minutes are one case.
LOST_PILGRIM_WINDOW_MINUTES = 15

_MOST_URGENT_FIRST = list(URGENCIES)


@dataclass
class Incident:
    type: str  # a code from schema.TYPES
    hotel: str | None
    loc_kind: str  # a code from schema.LOCATION_KINDS
    loc_number: str | None
    urgency: str  # the most urgent of its messages
    report_ids: list[int]  # in the order the messages were sent
    first_at: datetime
    last_at: datetime
    stays_alone: bool = False  # True: its report could not be merged, so nothing may join it either
    closed_at: datetime | None = None  # set by close_incident(); then the incident takes no more reports
    closed_by: str | None = None  # who closed it

    @property
    def message_count(self) -> int:
        return len(self.report_ids)


def can_merge(report: Understanding) -> bool:
    """True when we are sure enough of the type and the place to merge this report."""
    return report.type != "unclear" and report.loc_number is not None and not report.needs_confirmation


def _may_take(incident: Incident, report: Understanding, sent_at: datetime, window: timedelta) -> bool:
    """True when this open incident is about the same problem in the same place, and recent enough."""
    return (
        not incident.stays_alone
        and incident.closed_at is None
        and (incident.type, incident.hotel, incident.loc_kind, incident.loc_number)
        == (report.type, report.hotel, report.loc_kind, report.loc_number)
        and sent_at - incident.last_at <= window
    )


def _same_lost_pilgrim(incident: Incident, report: Understanding, sent_at: datetime) -> bool:
    """True when this open case is a lost pilgrim at the same hotel, reported a short while ago."""
    return (
        incident.type == report.type == "lost_pilgrim"
        and incident.closed_at is None
        and incident.hotel is not None
        and incident.hotel == report.hotel
        and sent_at - incident.last_at <= timedelta(minutes=LOST_PILGRIM_WINDOW_MINUTES)
    )


def add_report(
    incidents: list[Incident],
    report_id: int,
    sent_at: datetime,
    report: Understanding,
    window_minutes: int = MERGE_WINDOW_MINUTES,
) -> Incident | None:
    """Puts one report into the list of incidents and returns the incident it landed in.

    The report joins an incident that may take it, or starts a new incident,
    which is added to the end of the list. A message that is not a report makes
    no incident: the list is left alone and None is returned.
    """
    if not report.is_report:
        return None
    window = timedelta(minutes=window_minutes)
    for incident in reversed(incidents):  # the latest incident first
        usual = can_merge(report) and _may_take(incident, report, sent_at, window)
        if usual or _same_lost_pilgrim(incident, report, sent_at):
            incident.report_ids.append(report_id)
            incident.last_at = sent_at
            incident.urgency = min(incident.urgency, report.urgency, key=_MOST_URGENT_FIRST.index)
            return incident
    incident = Incident(
        type=report.type,
        hotel=report.hotel,
        loc_kind=report.loc_kind,
        loc_number=report.loc_number,
        urgency=report.urgency,
        report_ids=[report_id],
        first_at=sent_at,
        last_at=sent_at,
        stays_alone=not can_merge(report),
    )
    incidents.append(incident)
    return incident


def group_reports(arrivals, window_minutes: int = MERGE_WINDOW_MINUTES) -> list[Incident]:
    """Groups reports into incidents. arrivals is a list of (report id, time sent, report)."""
    incidents = []
    for report_id, sent_at, report in sorted(arrivals, key=lambda arrival: arrival[1]):
        add_report(incidents, report_id, sent_at, report, window_minutes)
    return incidents


def close_incident(incident: Incident, closed_by: str, at: datetime) -> Incident:
    """Closes an incident: the only way an incident is ever closed.

    closed_by says who closed it and at says when. Both are kept on the incident.
    """
    if not (closed_by or "").strip():
        raise ValueError("An incident cannot be closed without saying who closes it.")
    if incident.closed_at is not None:
        raise ValueError(f"This incident was already closed by {incident.closed_by}.")
    incident.closed_at = at
    incident.closed_by = closed_by.strip()
    return incident
