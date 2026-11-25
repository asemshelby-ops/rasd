"""The engine the pages talk to: reads a message, writes down a voice note, reads the mock card.

The pages only know these four things (read, transcribe, read_card, elm), so a
test can put a stand-in in their place. There are two engines:

  LiveEngine     the real thing: Claude for reading, the transcriber for voice.
  ReplayEngine   the safety net for the demo: answers the demo scene from files
                 saved beforehand, with no network at all.

The operator chooses between them on the /operator page.
"""

import hashlib
import json
from pathlib import Path

from demo.scene import SCENE_DIR
from rasd.cards import CardReading, read_mock_card
from rasd.elm import SimulatedElm
from rasd.understand import Reading, Understanding, build_report, make_client, not_understood, understand
from rasd.voice import SavedTranscripts, make_transcriber

# In front of an audience a stuck call is worse than a failed one: give up
# after this many seconds, and try once more only. A report that could not be
# read goes to the supervisor, so nothing is lost.
LIVE_TIMEOUT_SECONDS = 12.0
LIVE_RETRIES = 1

SAVED_READINGS_FILE = "saved_readings.json"


class LiveEngine:
    """The real thing: Claude for reading, the transcriber for voice, the simulated Elm lookup."""

    def __init__(self, client=None, scene_folder: Path = SCENE_DIR):
        self.client = client or make_client().with_options(timeout=LIVE_TIMEOUT_SECONDS, max_retries=LIVE_RETRIES)
        self.transcriber = make_transcriber(scene_folder)
        self.elm = SimulatedElm()

    def read(self, text: str, photo_attached: bool = False) -> Understanding:
        return understand(text, self.client, photo_attached=photo_attached)

    def transcribe(self, audio: bytes, filename: str) -> str:
        return self.transcriber.transcribe(audio, filename)

    def read_card(self, image: bytes, media_type: str) -> CardReading | None:
        return read_mock_card(image, media_type, self.client)


class ReplayEngine:
    """Answers the demo scene from saved files. Nothing here uses the network.

    The saved readings are what the real model answered when
    `python -m demo.record_scene` was run; the rest of each report (priority,
    owner, deadline) is worked out again from today's tables.

    otherwise() gives the live engine, for a message that is not part of the
    saved scene. When there is none, such a message goes to the supervisor.
    """

    def __init__(self, scene_folder: Path = SCENE_DIR, otherwise=None):
        saved = json.loads((scene_folder / SAVED_READINGS_FILE).read_text(encoding="utf-8"))
        self.readings = {text: Reading(**fields) for text, fields in saved["readings"].items()}
        card = saved["card"]
        self.card_key = hashlib.sha256((scene_folder / card["file"]).read_bytes()).hexdigest()
        self.card = CardReading(is_marked_as_specimen=True, full_name=card["full_name"], visa_number=card["visa_number"])
        self.transcripts = SavedTranscripts.from_folder(scene_folder)
        self.elm = SimulatedElm()
        self.otherwise = otherwise

    def read(self, text: str, photo_attached: bool = False) -> Understanding:
        if text in self.readings:
            return build_report(text, self.readings[text], photo_attached=photo_attached)
        if self.otherwise is not None:
            try:
                return self.otherwise().read(text, photo_attached=photo_attached)
            except Exception:  # no key, no network: whatever it is, a person reads the message
                pass
        return not_understood("replay mode: this message is not part of the saved scene", photo_attached=photo_attached)

    def transcribe(self, audio: bytes, filename: str) -> str:
        return self.transcripts.transcribe(audio, filename)

    def read_card(self, image: bytes, media_type: str) -> CardReading | None:
        return self.card if hashlib.sha256(image).hexdigest() == self.card_key else None
