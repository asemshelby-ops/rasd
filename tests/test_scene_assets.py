"""The saved files of the demo scene, and the whole scene played through the pages.

The voice notes are read from demo/scene/ exactly as the replay will read them.
Reading a message and reading the card are stand-ins: no AI model, no network.
Every person, hotel, company and number in the scene is invented.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import copy
from app.main import create_app
from demo import make_scene_assets as scene
from rasd.cards import CardReading
from rasd.elm import SimulatedElm
from rasd.understand import Reading, build_report
from rasd.voice import SavedTranscripts

SCENE_DIR = Path(__file__).resolve().parent.parent / "demo" / "scene"
LOST = dict(
    type="lost_pilgrim", hotel="", location_kind="none", number_words="", location_number="",
    partial_words="", confidence="high",
)  # fmt: skip


class SceneEngine:
    """The saved voice notes are real files; reading them and the card is a stand-in."""

    def __init__(self):
        self.elm = SimulatedElm()
        self.transcriber = SavedTranscripts.from_folder(SCENE_DIR)
        self.readings = {
            scene.COUNTER_NOTE: Reading(**LOST, pilgrim_name="", risks=[{"kind": "elderly", "words": "حاج كبير في السن"}]),
            scene.PILGRIM_NOTE: Reading(**LOST, pilgrim_name="زاہد کریم", risks=[]),
        }

    def read(self, text, photo_attached=False):
        return build_report(text, self.readings[text], photo_attached=photo_attached)

    def transcribe(self, audio, filename):
        return self.transcriber.transcribe(audio, filename)

    def read_card(self, image, media_type):
        if image != (SCENE_DIR / scene.CARD_FILE).read_bytes():
            return None
        return CardReading(is_marked_as_specimen=True, full_name=scene.CARD_NAME, visa_number=scene.CARD_VISA)


class Clock:
    def __init__(self):
        self.now = datetime(2026, 12, 23, 10, 0, 0)

    def __call__(self):
        return self.now


@pytest.fixture
def site(tmp_path):
    clock = Clock()
    client = TestClient(create_app(engine=SceneEngine(), db_path=tmp_path / "rasd.db", now=clock))
    client.clock = clock
    return client


def voice(site, file_name):
    audio = (SCENE_DIR / file_name).read_bytes()
    return site.post("/api/voice", data={"hotel": scene.REPORTING_HOTEL}, files={"audio": (file_name, audio)})


def test_every_saved_voice_note_has_its_file_and_its_words():
    listed = json.loads((SCENE_DIR / "transcripts.json").read_text(encoding="utf-8"))["voice_notes"]
    assert listed == {scene.COUNTER_FILE: scene.COUNTER_NOTE, scene.PILGRIM_FILE: scene.PILGRIM_NOTE}
    saved = SavedTranscripts.from_folder(SCENE_DIR)
    for name, words in listed.items():
        assert saved.transcribe((SCENE_DIR / name).read_bytes(), name) == words


def test_the_two_voice_notes_are_two_different_files():
    assert (SCENE_DIR / scene.COUNTER_FILE).read_bytes() != (SCENE_DIR / scene.PILGRIM_FILE).read_bytes()


def test_the_mock_card_is_a_picture_and_its_holder_is_in_the_simulated_lookup():
    assert (SCENE_DIR / scene.CARD_FILE).read_bytes().startswith(b"\x89PNG")
    record = SimulatedElm().lookup(scene.CARD_NAME, scene.CARD_VISA)
    assert record is not None
    assert record.hotel != scene.REPORTING_HOTEL  # he is lost at the counter of another company's hotel


def test_the_scene_names_nobody_real():
    """The visa number of the scene is in the invented range, and the card says it is a mock."""
    assert scene.CARD_VISA.startswith("999000")
    assert "SPECIMEN" in scene.CARD_MARKS and "نموذج تجريبي" in scene.CARD_MARKS


def test_the_whole_scene_from_two_voice_notes_to_a_closed_case(site):
    # 1. the counter employee's Arabic voice note
    first = voice(site, scene.COUNTER_FILE).json()
    assert first["heard"] == scene.COUNTER_NOTE and first["merged"] is False
    # 2. the pilgrim's own Urdu voice note, four minutes later
    site.clock.now += timedelta(minutes=4)
    second = voice(site, scene.PILGRIM_FILE).json()
    # 3. one case, two reports
    assert second["merged"] is True and second["case_id"] == first["case_id"]
    (case,) = site.get("/api/board").json()["cases"]
    assert case["count_text"] == "بلاغان، حالة واحدة"
    assert case["type"] == copy.TYPES["lost_pilgrim"] and case["priority"] == "critical"
    assert scene.REPORTING_HOTEL in case["place"]
    # 4. the mock card, then the simulated lookup
    card = (SCENE_DIR / scene.CARD_FILE).read_bytes()
    found = site.post(f"/api/cases/{case['id']}/card", files={"photo": (scene.CARD_FILE, card, "image/png")})
    assert found.status_code == 200 and found.json()["identified"] is True
    view = site.get("/api/board").json()
    record = SimulatedElm().lookup(scene.CARD_NAME, scene.CARD_VISA)
    assert view["cases"][0]["identified"] == {
        "company": record.company, "hotel": record.hotel, "room": record.room, "supervisor": record.supervisor,
    }  # fmt: skip
    # 5. his own company's supervisor is notified, on screen, marked as simulated
    (note,) = view["notifications"]
    assert record.supervisor in note["text"] and record.company in note["text"] and copy.SIMULATED in note["text"]
    # 6. one tap closes it, with the time and who closed it
    site.clock.now += timedelta(minutes=6)
    assert site.post(f"/api/cases/{case['id']}/close", data={"who": record.supervisor}).status_code == 200
    (closed,) = site.get("/api/board").json()["cases"]
    assert closed["state"] == "closed" and closed["closed_by"] == record.supervisor
    assert closed["closed_at"] == "2026-12-23T10:10:00"
    events = site.get(f"/api/cases/{case['id']}/events").json()["events"]
    # Nobody pressed "acknowledge" in this scene, and the history says so instead of leaving it out.
    assert [event["what"] for event in events] == ["reported", "reported", "identified", "skipped in_progress", "closed"]
    assert events[-1]["who"] == record.supervisor and events[-1]["at"] == "2026-12-23T10:10:00"


def test_nothing_private_from_the_scene_reaches_the_big_screen(site):
    voice(site, scene.COUNTER_FILE)
    reply = voice(site, scene.PILGRIM_FILE).json()
    card = (SCENE_DIR / scene.CARD_FILE).read_bytes()
    site.post(f"/api/cases/{reply['case_id']}/card", files={"photo": (scene.CARD_FILE, card, "image/png")})
    shown = site.get("/board").text + site.get("/api/board").text
    assert scene.CARD_VISA not in shown
    assert scene.CARD_NAME not in shown and "زاہد کریم" not in shown
    assert "ز · بلاغ 1" in shown
