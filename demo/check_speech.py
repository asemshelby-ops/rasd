"""Tries the live speech-to-text service on ONE recording, to see that the key works.

    python -m demo.check_speech "C:\\rasd-private\\test.m4a"
    python -m demo.check_speech "C:\\rasd-private\\test.m4a" --read     also show what Rasd makes of the words

It needs RASD_OPENAI_KEY (in the .env file). One short recording costs a
fraction of a cent ($0.006 per minute). Use an invented report: no real pilgrim.
The words are printed and also saved next to the recording, because a Windows
terminal may not show Arabic.
"""

import argparse
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from rasd.voice import OPENAI_KEY_VARIABLE, OpenAITranscriber, VoiceError

PROJECT_DIR = Path(__file__).resolve().parent.parent


def check(recording: Path, transcriber, read=None) -> int:
    """Transcribes one recording and prints what came back. read(text) shows Rasd's reading, when given."""
    started = time.perf_counter()
    try:
        words = transcriber.transcribe(recording.read_bytes(), recording.name)
    except VoiceError as e:
        print(f"Stopped: {e}", file=sys.stderr)
        return 1
    seconds = time.perf_counter() - started
    lines = [f"Words heard: {words or '(nothing)'}", f"Seconds: {seconds:.2f}"]
    if read is not None and words:
        report = read(words)
        lines += [
            f"Rasd reads it as: type={report.type}, hotel={report.hotel}, place={report.loc_kind} {report.loc_number}, "
            f"priority={report.urgency}, to the supervisor={report.needs_confirmation} {list(report.reasons)}"
        ]
    saved = recording.with_name(recording.stem + ".heard.txt")
    saved.write_text("\n".join(lines) + "\n", encoding="utf-8")
    for line in lines:
        try:
            print(line)
        except UnicodeEncodeError:
            print("(this terminal cannot show Arabic)")
    print(f"Saved to: {saved}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Try live speech to text on one recording.")
    parser.add_argument("recording", help="a short voice recording: m4a, mp3, wav or webm")
    parser.add_argument("--read", action="store_true", help="also read the words with Rasd (one Claude call)")
    options = parser.parse_args(argv)
    load_dotenv(PROJECT_DIR / ".env")
    key = os.environ.get(OPENAI_KEY_VARIABLE, "").strip()
    if not key:
        print(f"Stopped: {OPENAI_KEY_VARIABLE} is not set. Put the key in the .env file: {OPENAI_KEY_VARIABLE}=...", file=sys.stderr)
        return 2
    recording = Path(options.recording)
    if not recording.is_file():
        print(f"Stopped: there is no file at '{recording}'.", file=sys.stderr)
        return 2
    read = None
    if options.read:
        from rasd.understand import make_client, understand

        client = make_client()
        read = lambda words: understand(words, client)  # noqa: E731
    return check(recording, OpenAITranscriber(key), read)


if __name__ == "__main__":
    sys.exit(main())
