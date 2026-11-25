"""Speech to text, behind one small interface.

    text = transcriber.transcribe(audio_bytes, "note.m4a")

Claude takes no audio, so a voice note is first written down by a transcriber:

  OpenAITranscriber   the live path: OpenAI gpt-4o-transcribe. Needs RASD_OPENAI_KEY.
  SavedTranscripts    the replay path: the text of voice notes that were saved
                      beforehand, found by the content of the audio file.
  NoTranscriber       when neither is available: every voice note is an error
                      that says what to do.

A transcriber raises VoiceError when it cannot write a note down. The pages
turn that into a message for the sender; nothing crashes.
"""

import hashlib
import json
import os
from pathlib import Path
from typing import Protocol

import httpx2

OPENAI_KEY_VARIABLE = "RASD_OPENAI_KEY"
OPENAI_MODEL = "gpt-4o-transcribe"


class VoiceError(Exception):
    """A voice note could not be turned into text. The message says why, in simple English."""


class Transcriber(Protocol):
    def transcribe(self, audio: bytes, filename: str) -> str:
        """The words of a voice note. Raises VoiceError when it cannot."""


class NoTranscriber:
    def transcribe(self, audio: bytes, filename: str) -> str:
        raise VoiceError(
            f"speech to text is not set up: {OPENAI_KEY_VARIABLE} is missing and this voice note was not saved beforehand"
        )


class SavedTranscripts:
    """The replay path: voice notes whose text was saved beforehand."""

    def __init__(self, text_by_key: dict[str, str]):
        self.text_by_key = text_by_key

    @staticmethod
    def key_of(audio: bytes) -> str:
        """What identifies a saved voice note: a fingerprint of its bytes."""
        return hashlib.sha256(audio).hexdigest()

    @classmethod
    def from_folder(cls, folder: Path) -> "SavedTranscripts":
        """Reads folder/transcripts.json: {"file name": "the words said in it"}."""
        listed = json.loads((folder / "transcripts.json").read_text(encoding="utf-8"))["voice_notes"]
        return cls({cls.key_of((folder / name).read_bytes()): text for name, text in listed.items()})

    def transcribe(self, audio: bytes, filename: str) -> str:
        text = self.text_by_key.get(self.key_of(audio))
        if text is None:
            raise VoiceError("this voice note is not one of the saved ones, and live speech to text is not set up")
        return text


class OpenAITranscriber:
    """The live path: OpenAI's transcription service. Tested with the network replaced; never yet run for real."""

    URL = "https://api.openai.com/v1/audio/transcriptions"

    def __init__(self, key: str, timeout: float = 20.0, client=None):
        self.key = key
        self.timeout = timeout
        self.client = client or httpx2  # tests pass a client whose network is replaced

    def transcribe(self, audio: bytes, filename: str) -> str:
        try:
            response = self.client.post(
                self.URL,
                headers={"Authorization": f"Bearer {self.key}"},
                data={"model": OPENAI_MODEL},
                files={"file": (filename, audio)},
                timeout=self.timeout,
            )
        except httpx2.HTTPError:
            raise VoiceError("could not reach the speech-to-text service (network problem or timeout)") from None
        status = response.status_code
        if status == 401:
            raise VoiceError(f"the speech-to-text key was rejected (401): check {OPENAI_KEY_VARIABLE}")
        if status == 429:
            raise VoiceError("the speech-to-text service refused (429): too many requests, or no credit left on the account")
        if status in (400, 413, 415):
            raise VoiceError(f"the service could not use this recording ({status}): use m4a, mp3, wav or webm, under 25 MB")
        if status != 200:
            raise VoiceError(f"the speech-to-text service answered with error {status}")
        return response.json().get("text", "").strip()


class FirstThatWorks:
    """Tries each transcriber in turn: the live one first, then the saved notes."""

    def __init__(self, *transcribers):
        self.transcribers = transcribers

    def transcribe(self, audio: bytes, filename: str) -> str:
        problem, first_problem, heard_nothing = VoiceError("no transcriber is set up"), None, False
        for transcriber in self.transcribers:
            try:
                text = transcriber.transcribe(audio, filename)
            except VoiceError as e:
                problem = first_problem = first_problem or e  # the first failure says the most
                continue
            if text.strip():
                return text
            heard_nothing = True  # it answered, with no words: let the next one try
        if heard_nothing:
            return ""
        raise problem


def make_transcriber(saved_folder: Path | None = None) -> Transcriber:
    """The transcriber for this machine: live if the key is set, with the saved notes as a fallback."""
    parts = []
    # A saved voice note is known by its bytes, so its saved words come first: no call is made for it.
    if saved_folder is not None and (saved_folder / "transcripts.json").exists():
        parts.append(SavedTranscripts.from_folder(saved_folder))
    key = os.environ.get(OPENAI_KEY_VARIABLE, "").strip()
    if key:
        parts.append(OpenAITranscriber(key))
    return FirstThatWorks(*parts) if parts else NoTranscriber()
