"""The Elm lookup: who a pilgrim belongs to, from the name and the visa number.

THIS IS A SIMULATION. There is no connection to Elm or to any real register.
SimulatedElm answers from a small file of invented pilgrims
(data/simulated_elm.json). Every screen that shows its answer says "محاكاة".

The rest of Rasd only knows the small interface ElmDirectory, so a real
service can replace the simulation later without touching anything else.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

RECORDS_FILE = Path(__file__).resolve().parent.parent / "data" / "simulated_elm.json"


@dataclass(frozen=True)
class PilgrimRecord:
    """What the lookup returns about one pilgrim. All of it is invented."""

    name: str
    company: str
    hotel: str
    room: str
    supervisor: str
    visa_number: str = field(repr=False, default="")  # never printed


class ElmDirectory(Protocol):
    def lookup(self, name: str, visa_number: str) -> PilgrimRecord | None:
        """The pilgrim with this name and visa number, or None."""


def _same_name(a: str, b: str) -> bool:
    return " ".join(a.upper().split()) == " ".join(b.upper().split()) != ""


class SimulatedElm:
    """Answers lookups from the file of invented pilgrims. Nothing leaves the laptop."""

    SIMULATED = True

    def __init__(self, records_file: Path = RECORDS_FILE):
        self.records = json.loads(records_file.read_text(encoding="utf-8"))["pilgrims"]

    def lookup(self, name: str, visa_number: str) -> PilgrimRecord | None:
        for record in self.records:
            if record["visa_number"] == visa_number.strip() and _same_name(record["name"], name):
                return PilgrimRecord(**record)
        return None
