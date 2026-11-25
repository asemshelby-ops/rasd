"""Records what the real model reads in the demo scene, for the replay switch.

    python -m demo.record_scene

It reads the two voice-note texts and the mock card ONCE with the real model
(three calls, well under one cent) and writes demo/scene/saved_readings.json.
In replay mode the pages answer from that file, with no network.

Run it again after changing the scene's words, the mock card or the prompt.
It refuses to save a recording with which the scene would not work.
"""

import json
import sys
from datetime import date

from demo import scene
from rasd.cards import read_mock_card
from rasd.cost import cost_usd
from rasd.privacy import redact
from rasd.understand import DEFAULT_MODEL, ask_model, build_report, make_client

SAVED_FILE = scene.SCENE_DIR / "saved_readings.json"


def main() -> None:
    client = make_client()
    spent = 0.0
    readings = {}
    for words in (scene.COUNTER_NOTE, scene.PILGRIM_NOTE):
        reply = ask_model(redact(words)[0], client)
        spent += cost_usd(DEFAULT_MODEL, reply.usage.input_tokens, reply.usage.output_tokens)
        if reply.parsed_output is None:
            sys.exit(f"Nothing saved: the model gave no reading (stop reason: {reply.stop_reason}). Run it again.")
        report = build_report(words, reply.parsed_output)
        if report.type != "lost_pilgrim":
            sys.exit(f"Nothing saved: a voice note was read as '{report.type}', not as a lost pilgrim. Run it again.")
        readings[words] = reply.parsed_output.model_dump()

    card = read_mock_card((scene.SCENE_DIR / scene.CARD_FILE).read_bytes(), "image/png", client)
    if card is None or (card.full_name, card.visa_number) != (scene.CARD_NAME, scene.CARD_VISA):
        sys.exit("Nothing saved: the mock card was not read as printed. Check demo/scene/mock_card.png and run it again.")

    saved = {
        "note": "What the real model read in the demo scene. Written by `python -m demo.record_scene`; do not edit by hand.",
        "recorded_on": date.today().isoformat(),
        "model": DEFAULT_MODEL,
        "readings": readings,
        "card": {"file": scene.CARD_FILE, "full_name": card.full_name, "visa_number": card.visa_number},
    }
    SAVED_FILE.write_text(json.dumps(saved, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved the scene's readings to {SAVED_FILE}")
    print(f"Approximate API cost: ${spent:.4f} for the two readings (the card call is a few hundredths of a cent more)")


if __name__ == "__main__":
    main()
