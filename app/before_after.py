"""Builds the before-and-after page: an invented WhatsApp group, and Rasd's reading of the same messages.

    python -m app.before_after        reads demo/whatsapp_group.json with the real engine (a few
                                      cents at most) and writes demo/before_after.json

The "after" side is not written by hand: every card on it is what Rasd made of
the message, through the same intake and the same board rules as the live
pages. Run the command again after changing the group or the prompt.
"""

import json
from datetime import datetime
from pathlib import Path

from app.intake import take_in
from app.store import Store
from rasd.askback import ask_back

DEMO_DIR = Path(__file__).resolve().parent.parent / "demo"
GROUP_FILE = DEMO_DIR / "whatsapp_group.json"
SCENE_FILE = DEMO_DIR / "before_after.json"
DAY = datetime(2026, 12, 23)  # the invented day of the group


def build_scene(messages: list[dict], read) -> dict:
    """The two sides of the page. read(text, photo_attached) is the engine's reader."""
    store = Store(":memory:")
    questions, not_reports, last = {}, 0, DAY
    for message in messages:
        hour, minute = (int(part) for part in message["time"].split(":"))
        last = DAY.replace(hour=hour, minute=minute)
        _, case_id, joined, report = take_in(
            store, read, message["text"], "", bool(message.get("photo")), "group", last
        )
        if case_id is None:
            not_reports += 1
        elif not joined:
            question = ask_back(report)
            questions[case_id] = question.text if question else None
    cases = [
        {
            "label": case["label"],
            "type": case["type"],
            "place": case["place"],
            "priority": case["priority"],
            "priority_label": case["priority_label"],
            "owner": case["owner"],
            "state": case["state"],
            "count_text": case["count_text"] if case["count"] > 1 else None,
            "question": questions[case["id"]],
            "photo": case["photo_attached"],
        }
        for case in store.board(last)
    ]
    return {"messages": messages, "cases": cases, "not_reports": not_reports}


def main() -> None:
    from app.engine import LiveEngine
    from rasd.cost import cost_usd
    from rasd.understand import DEFAULT_MODEL

    engine = LiveEngine()
    spent = {"input": 0, "output": 0}

    def read(text, photo_attached=False):
        report = engine.read(text, photo_attached=photo_attached)
        spent["input"] += report.input_tokens
        spent["output"] += report.output_tokens
        return report

    group = json.loads(GROUP_FILE.read_text(encoding="utf-8"))
    scene = build_scene(group["messages"], read)
    scene["note"] = (
        "Written by `python -m app.before_after`. The cases are Rasd's own reading of the invented messages "
        f"in whatsapp_group.json, made on {datetime.now():%Y-%m-%d}. Do not edit by hand."
    )
    SCENE_FILE.write_text(json.dumps(scene, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {SCENE_FILE.name}: {len(scene['cases'])} cases, {scene['not_reports']} messages that are not reports.")
    print(f"Approximate API cost: ${cost_usd(DEFAULT_MODEL, spent['input'], spent['output']):.4f}")


if __name__ == "__main__":
    main()
