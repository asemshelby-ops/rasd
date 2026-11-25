"""Where the pages keep reports and cases: one SQLite file.

What is in it:
  reports          every message that came in, with the engine's reading of it
  cases            what the board shows; a case holds one or more reports
  events           the log: who did what to a case, and when
  private_numbers  passport and visa numbers. Nothing reads this table for a page.
  notifications    simulated notifications shown on the board

Merging uses the tested rules in rasd/incidents.py; nothing is decided here.
"""

import json
import sqlite3
import threading
from dataclasses import asdict, replace
from datetime import datetime, timedelta
from pathlib import Path

from app import copy
from rasd.askback import answer, ask_back
from rasd.cases import replacement_request
from rasd.display import screen_label
from rasd.incidents import Incident, add_report, can_merge, close_incident
from rasd.privacy import PrivateNumbers
from rasd.routing import ACKNOWLEDGE_MINUTES, DEADLINE_MINUTES, HOTELS, OWNER_BY_TYPE
from rasd.schema import URGENCIES
from rasd.understand import Understanding

TABLES = """
create table if not exists reports (
    id integer primary key, case_id integer, received_at text, reporting_hotel text,
    source text, safe_text text, report text);
create table if not exists cases (
    id integer primary key, incident text, pilgrim_name text, photo_attached integer default 0,
    waiting integer default 0, acknowledged_at text, acknowledged_by text, identified text, replacement text);
create table if not exists events (id integer primary key, case_id integer, at text, who text, what text);
create table if not exists private_numbers (
    id integer primary key, report_id integer, case_id integer, kind text, value text);
create table if not exists notifications (id integer primary key, case_id integer, at text, text text);
create table if not exists settings (name text primary key, value text);
"""

# How a report reached us. "saved" is a voice note the operator sent from the saved scene files.
SAVED_SOURCE = "saved"


class CaseClosed(Exception):
    pass


class NoSuchCase(Exception):
    pass


class NothingToAnswer(Exception):
    pass


def _report_to_json(report: Understanding) -> str:
    return json.dumps(asdict(report), ensure_ascii=False)


def _report_from_json(text: str) -> Understanding:
    fields = json.loads(text)
    for name in ("reasons", "risks", "risk_words"):
        fields[name] = tuple(fields[name])
    return Understanding(**fields)


def _screen_hotel(hotel: str | None) -> str | None:
    """A hotel as the big screen may show it. A name that is not in the team's list is words
    from a message (it could be a person's name), so the screen only says that it is not listed."""
    return hotel if hotel is None or hotel in HOTELS else copy.UNLISTED_HOTEL


def _incident_to_json(incident: Incident) -> str:
    fields = asdict(incident)
    for name in ("first_at", "last_at", "closed_at"):
        fields[name] = fields[name].isoformat() if fields[name] else None
    return json.dumps(fields, ensure_ascii=False)


def _incident_from_json(text: str) -> Incident:
    fields = json.loads(text)
    for name in ("first_at", "last_at", "closed_at"):
        fields[name] = datetime.fromisoformat(fields[name]) if fields[name] else None
    return Incident(**fields)


class Store:
    def __init__(self, path: Path):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(TABLES)
        self.lock = threading.Lock()  # the pages are served from several threads

    # --- settings and clearing ------------------------------------------------------------

    def setting(self, name: str, default: str) -> str:
        with self.lock:
            row = self.db.execute("select value from settings where name = ?", (name,)).fetchone()
        return row["value"] if row else default

    def set_setting(self, name: str, value: str) -> None:
        with self.lock, self.db:
            self.db.execute("insert or replace into settings (name, value) values (?, ?)", (name, value))

    def clear(self) -> None:
        """Empties the board between two demos. Settings (the live or replay mode) stay."""
        with self.lock, self.db:
            for table in ("reports", "cases", "events", "private_numbers", "notifications"):
                self.db.execute(f"delete from {table}")

    def open_lost_pilgrim_case(self) -> int | None:
        """The latest lost-pilgrim case that is still open, for the operator's card step."""
        with self.lock:
            rows = self.db.execute("select id, incident from cases order by id desc").fetchall()
        for row in rows:
            incident = _incident_from_json(row["incident"])
            if incident.type == "lost_pilgrim" and incident.closed_at is None:
                return row["id"]
        return None

    # --- reports coming in ---------------------------------------------------------------

    def add_report(
        self,
        report: Understanding,
        received_at: datetime,
        reporting_hotel: str | None,
        source: str,
        safe_text: str,
        private: PrivateNumbers = PrivateNumbers(),
    ) -> tuple[int, int | None, bool]:
        """Saves a report and puts it in a case. Returns (report id, case id or None, joined an existing case)."""
        with self.lock, self.db:
            report_id = self.db.execute(
                "insert into reports (received_at, reporting_hotel, source, safe_text, report) values (?, ?, ?, ?, ?)",
                # The words of a message that is not a report are not kept: only that it came.
                (received_at.isoformat(), reporting_hotel, source, safe_text if report.is_report else "", _report_to_json(report)),
            ).lastrowid
            if not report.is_report:
                return report_id, None, False

            rows = self.db.execute("select id, incident from cases order by id").fetchall()
            incidents = [_incident_from_json(row["incident"]) for row in rows]
            incident = add_report(incidents, report_id, received_at, report)
            position = next((i for i, known in enumerate(incidents[: len(rows)]) if known is incident), None)
            joined = position is not None
            if joined:
                case_id = rows[position]["id"]
                self.db.execute("update cases set incident = ? where id = ?", (_incident_to_json(incident), case_id))
            else:
                case_id = self.db.execute(
                    "insert into cases (incident, waiting) values (?, ?)",
                    (_incident_to_json(incident), int(report.needs_confirmation)),
                ).lastrowid
            self.db.execute("update reports set case_id = ? where id = ?", (case_id, report_id))
            self._absorb(case_id, report, received_at)
            for kind in ("passport", "visa", "other"):
                for value in getattr(private, kind):
                    self.db.execute(
                        "insert into private_numbers (report_id, case_id, kind, value) values (?, ?, ?, ?)",
                        (report_id, case_id, kind, value),
                    )
            self._log(case_id, received_at, source, "reported")
            return report_id, case_id, joined

    def _absorb(self, case_id: int, report: Understanding, at: datetime) -> None:
        """Takes into the case what a report adds to it: a name, a photo, a replacement request."""
        case = self.db.execute("select * from cases where id = ?", (case_id,)).fetchone()
        if report.pilgrim_name and not case["pilgrim_name"]:
            self.db.execute("update cases set pilgrim_name = ? where id = ?", (report.pilgrim_name, case_id))
        if report.photo_attached:
            self.db.execute("update cases set photo_attached = 1 where id = ?", (case_id,))
        request = replacement_request(report, at)
        if request and not case["replacement"]:
            saved = {
                "hotel": request.hotel,
                "room": request.room,
                "reported_at": request.reported_at.isoformat(),
                "due_at": request.due_at.isoformat(),
                "missing": list(request.missing),
            }
            self.db.execute("update cases set replacement = ? where id = ?", (json.dumps(saved, ensure_ascii=False), case_id))

    def _log(self, case_id: int, at: datetime, who: str, what: str) -> None:
        self.db.execute(
            "insert into events (case_id, at, who, what) values (?, ?, ?, ?)", (case_id, at.isoformat(), who, what)
        )

    def report(self, report_id: int) -> tuple[Understanding, int | None]:
        row = self.db.execute("select report, case_id from reports where id = ?", (report_id,)).fetchone()
        if row is None:
            raise NoSuchCase
        return _report_from_json(row["report"]), row["case_id"]

    def _join_open_case(self, case_id: int, report_id: int, report: Understanding) -> int | None:
        """Runs the duplicate check again for a report that is a case of its own, against the other cases.

        When the tested merge rules (rasd/incidents.py) put it into another open case, the report
        moves there with everything that belongs to it, its own card is removed, and that case's
        id is returned. Otherwise nothing changes and None is returned. The merge window is
        counted from when the report was SENT, not from now.
        """
        sent_at = datetime.fromisoformat(
            self.db.execute("select received_at from reports where id = ?", (report_id,)).fetchone()["received_at"]
        )
        rows = self.db.execute("select id, incident from cases where id != ? order by id", (case_id,)).fetchall()
        others = [_incident_from_json(row["incident"]) for row in rows]
        landed = add_report(others, report_id, sent_at, report)
        position = next((i for i, known in enumerate(others[: len(rows)]) if known is landed), None)
        if position is None:
            return None
        target = rows[position]["id"]
        self.db.execute("update cases set incident = ? where id = ?", (_incident_to_json(landed), target))
        for table in ("reports", "private_numbers", "events", "notifications"):
            column = "id" if table == "reports" else "case_id"
            value = report_id if table == "reports" else case_id
            self.db.execute(f"update {table} set case_id = ? where {column} = ?", (target, value))
        self.db.execute("delete from cases where id = ?", (case_id,))
        return target

    def answer_question(self, report_id: int, reply: str, at: datetime) -> tuple[Understanding, int | None, bool]:
        """The sender's reply fills the same report. Raises NothingToAnswer when no question is open.

        Returns (the report, its case, whether the reply made it join another open case).
        """
        with self.lock, self.db:
            report, case_id = self.report(report_id)
            question = ask_back(report)
            if question is None:
                raise NothingToAnswer
            completed = answer(report, question, reply)
            joined = False
            self.db.execute("update reports set report = ? where id = ?", (_report_to_json(completed), report_id))
            if case_id is not None:
                row = self.db.execute("select incident from cases where id = ?", (case_id,)).fetchone()
                incident = _incident_from_json(row["incident"])
                if incident.report_ids == [report_id]:  # the case is this one report: it follows the report
                    incident = replace(
                        incident,
                        type=completed.type,
                        hotel=completed.hotel,
                        loc_kind=completed.loc_kind,
                        loc_number=completed.loc_number,
                        urgency=completed.urgency,
                        pilgrim_name=completed.pilgrim_name or incident.pilgrim_name,
                        stays_alone=not can_merge(completed),
                    )
                    self.db.execute(
                        "update cases set incident = ?, waiting = ? where id = ?",
                        (_incident_to_json(incident), int(completed.needs_confirmation), case_id),
                    )
                # Any answer that fills in the hotel, the room, the floor or the type may make the
                # report a duplicate of an open case, so the duplicate check runs again (owner's
                # decision). A reply that only gives a name changes none of these and does not run it.
                def what_merging_looks_at(r: Understanding) -> tuple:
                    return (r.type, r.hotel, r.loc_kind, r.loc_number)

                changed = what_merging_looks_at(completed) != what_merging_looks_at(report)
                if changed and incident.report_ids == [report_id]:
                    target = self._join_open_case(case_id, report_id, completed)
                    if target is not None:
                        case_id, joined = target, True
                self._absorb(case_id, completed, at)
                self._log(case_id, at, "sender", "answered")
            return completed, case_id, joined

    # --- what people do to a case ----------------------------------------------------------

    def _incident(self, case_id: int) -> Incident:
        row = self.db.execute("select incident from cases where id = ?", (case_id,)).fetchone()
        if row is None:
            raise NoSuchCase
        return _incident_from_json(row["incident"])

    def confirm(self, case_id: int, who: str, at: datetime) -> None:
        """The supervisor confirms a waiting case. What waited for that (a lost card's 24-hour clock) starts now."""
        with self.lock, self.db:
            self._incident(case_id)
            self.db.execute("update cases set waiting = 0 where id = ?", (case_id,))
            rows = self.db.execute("select received_at, report from reports where case_id = ? order by id", (case_id,)).fetchall()
            for row in rows:
                confirmed = replace(_report_from_json(row["report"]), needs_confirmation=False)
                self._absorb(case_id, confirmed, datetime.fromisoformat(row["received_at"]))  # counted from the report
            self._log(case_id, at, who, "confirmed")

    def is_open_lost_pilgrim(self, case_id: int) -> bool:
        with self.lock:
            row = self.db.execute("select incident from cases where id = ?", (case_id,)).fetchone()
        if row is None:
            return False
        incident = _incident_from_json(row["incident"])
        return incident.type == "lost_pilgrim" and incident.closed_at is None

    def acknowledge(self, case_id: int, who: str, at: datetime) -> None:
        with self.lock, self.db:
            if self._incident(case_id).closed_at is not None:
                raise CaseClosed
            changed = self.db.execute(
                "update cases set acknowledged_at = ?, acknowledged_by = ? where id = ? and acknowledged_at is null",
                (at.isoformat(), who, case_id),
            ).rowcount
            if changed:  # the first acknowledgement is the one that counts, and the only one logged
                self._log(case_id, at, who, "acknowledged")

    def close(self, case_id: int, who: str, at: datetime) -> None:
        """Closes a case through the one close action, which records the time and who closed it."""
        with self.lock, self.db:
            incident = self._incident(case_id)
            if incident.closed_at is not None:
                raise CaseClosed
            close_incident(incident, closed_by=who, at=at)
            self.db.execute("update cases set incident = ? where id = ?", (_incident_to_json(incident), case_id))
            self._log(case_id, at, incident.closed_by, "closed")

    def identify(self, case_id: int, name: str, visa_number: str, record, at: datetime) -> str:
        """Records who the pilgrim is (from the simulated lookup) and the simulated notification. Returns its text."""
        with self.lock, self.db:
            incident = self._incident(case_id)
            found = {"company": record.company, "hotel": record.hotel, "room": record.room, "supervisor": record.supervisor}
            self.db.execute(
                "update cases set identified = ?, pilgrim_name = coalesce(pilgrim_name, ?) where id = ?",
                (json.dumps(found, ensure_ascii=False), name, case_id),
            )
            self.db.execute(
                "insert into private_numbers (report_id, case_id, kind, value) values (null, ?, 'visa', ?)",
                (case_id, visa_number),
            )
            text = copy.notification(record.supervisor, record.company, incident.hotel, case_id)
            self.db.execute(
                "insert into notifications (case_id, at, text) values (?, ?, ?)", (case_id, at.isoformat(), text)
            )
            self._log(case_id, at, "simulated lookup", "identified")
            return text

    # --- what the pages show. Nothing private leaves through these. --------------------------

    def board(self, now: datetime) -> list[dict]:
        """The cases as the big screen may show them: no full name, no number, no words of a message."""
        with self.lock:
            rows = self.db.execute("select * from cases order by id").fetchall()
            saved = self.db.execute("select distinct case_id from reports where source = ?", (SAVED_SOURCE,)).fetchall()
        from_saved = {row["case_id"] for row in saved}
        cases = [{**self._public(row, now), "from_saved": row["id"] in from_saved} for row in rows]
        order = list(URGENCIES)
        cases.sort(key=lambda case: (case["state"] == "closed", order.index(case["priority"]), case["first_at"]))
        return cases

    def _public(self, row, now: datetime) -> dict:
        incident = _incident_from_json(row["incident"])
        acknowledge_minutes = ACKNOWLEDGE_MINUTES.get(incident.urgency)
        acknowledge_due = incident.first_at + timedelta(minutes=acknowledge_minutes) if acknowledge_minutes else None
        close_due = incident.first_at + timedelta(minutes=DEADLINE_MINUTES[incident.urgency])
        acknowledged = row["acknowledged_at"] is not None
        next_due = acknowledge_due if acknowledge_due and not acknowledged else close_due
        if incident.closed_at is not None:
            state = "closed"
        elif now > next_due:
            state = "late"  # also when it still waits for the supervisor (owner's decision): see "waiting" below
        elif row["waiting"]:
            state = "waiting"
        else:
            state = "routed"
        found = json.loads(row["identified"]) if row["identified"] else None
        replacement = json.loads(row["replacement"]) if row["replacement"] else None
        return {
            "id": row["id"],
            # The number on the label is the one the first sender was told ("وصل البلاغ 7").
            "label": screen_label(incident.report_ids[0], row["pilgrim_name"]),
            "type": copy.TYPES[incident.type],
            "place": copy.place_text(_screen_hotel(incident.hotel), incident.loc_kind, incident.loc_number),
            "priority": incident.urgency,
            "priority_label": copy.URGENCIES[incident.urgency],
            "owner": copy.OWNERS[OWNER_BY_TYPE[incident.type]],
            "state": state,
            "waiting": bool(row["waiting"]) and state != "closed",  # the supervisor has not confirmed it yet
            "state_label": copy.STATES[state],
            "count": incident.message_count,
            "count_text": copy.count_text(incident.message_count),
            "photo_attached": bool(row["photo_attached"]),
            "first_at": incident.first_at.isoformat(),
            "acknowledge_due": acknowledge_due.isoformat() if acknowledge_due else None,
            "close_due": close_due.isoformat(),
            "acknowledged": acknowledged,
            "closed_at": incident.closed_at.isoformat() if incident.closed_at else None,
            "closed_by": incident.closed_by,
            "identified": found,
            "identified_text": copy.identified(**found) if found else None,
            "replacement_due": replacement["due_at"] if replacement else None,
        }

    def waiting(self, now: datetime) -> list[dict]:
        """For the supervisor's own page: each waiting case, why it waits, and the words of its messages.

        The words have their passport and visa numbers hidden. This never goes to the big screen.
        """
        waiting = [case for case in self.board(now) if case["waiting"]]
        with self.lock:
            for case in waiting:
                rows = self.db.execute("select safe_text, report from reports where case_id = ? order by id", (case["id"],)).fetchall()
                case["messages"] = [row["safe_text"] for row in rows]
                reasons = [reason for row in rows for reason in _report_from_json(row["report"]).reasons]
                case["reasons"] = [copy.FLAG_REASONS[reason] for reason in dict.fromkeys(reasons)]
        return waiting

    def notifications(self) -> list[dict]:
        with self.lock:
            rows = self.db.execute("select case_id, at, text from notifications order by id desc").fetchall()
        return [dict(row) for row in rows]

    def events(self, case_id: int) -> list[dict]:
        with self.lock:
            rows = self.db.execute("select what, who, at from events where case_id = ? order by id", (case_id,)).fetchall()
        return [dict(row) for row in rows]

    def replacement(self, case_id: int) -> dict | None:
        with self.lock:
            row = self.db.execute("select id, incident, pilgrim_name, replacement from cases where id = ?", (case_id,)).fetchone()
        if row is None or not row["replacement"]:
            return None
        saved = json.loads(row["replacement"])
        saved["hotel"] = _screen_hotel(saved["hotel"])
        first_report = _incident_from_json(row["incident"]).report_ids[0]
        return {"pilgrim": screen_label(first_report, row["pilgrim_name"]), **saved}

    def replacements(self) -> list[dict]:
        """Every live replacement request, for the Elm view."""
        with self.lock:
            rows = self.db.execute("select id, incident, pilgrim_name, identified, replacement from cases where replacement is not null").fetchall()
        requests = []
        for row in rows:
            found = json.loads(row["identified"]) if row["identified"] else None
            requests.append(
                {
                    "company": found["company"] if found else copy.OUR_COMPANY,
                    "label": screen_label(_incident_from_json(row["incident"]).report_ids[0], row["pilgrim_name"]),
                    "due_at": json.loads(row["replacement"])["due_at"],
                    "live": True,
                    "simulated": False,
                }
            )
        return requests
