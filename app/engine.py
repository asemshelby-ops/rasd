"""The engine the pages talk to: reads a message, writes down a voice note, reads the mock card.

The pages only know these four things, so a test can put a stand-in in its place.
"""

from pathlib import Path

from rasd.cards import CardReading, read_mock_card
from rasd.elm import SimulatedElm
from rasd.understand import Understanding, make_client, understand
from rasd.voice import make_transcriber

SCENE_DIR = Path(__file__).resolve().parent.parent / "demo" / "scene"


class LiveEngine:
    """The real thing: Claude for reading, the transcriber for voice, the simulated Elm lookup."""

    def __init__(self, client=None, scene_folder: Path = SCENE_DIR):
        self.client = client or make_client()
        self.transcriber = make_transcriber(scene_folder)
        self.elm = SimulatedElm()

    def read(self, text: str, photo_attached: bool = False) -> Understanding:
        return understand(text, self.client, photo_attached=photo_attached)

    def transcribe(self, audio: bytes, filename: str) -> str:
        return self.transcriber.transcribe(audio, filename)

    def read_card(self, image: bytes, media_type: str) -> CardReading | None:
        return read_mock_card(image, media_type, self.client)
