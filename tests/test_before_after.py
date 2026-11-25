"""The before-and-after page: an invented WhatsApp group, and the same messages as Rasd reads them.

The reading is a stand-in here: no AI model, no network. Everything is invented.
"""

import json
from pathlib import Path

from app import copy
from app.before_after import GROUP_FILE, build_scene
from rasd.understand import Reading, build_report

ATTENDANCE = "الحضور: مناوبة العصر كاملة"
NO_WATER = "الموية مقطوعة عن غرفة 318 في دار المنارة"
SICK = "الحاج زكريا في غرفة 220 بدار المنارة تعبان ويحتاج دواه"
LEAK_PHOTO = "شوفوا التسريب"
FOUND_IT = "لقيناها 👍"


def reading(**fields) -> Reading:
    base = dict(
        type="not_a_report", hotel="", location_kind="none", number_words="", location_number="", pilgrim_name="",
        risks=[], partial_words="", confidence="high",
    )  # fmt: skip
    base.update(fields)
    return Reading(**base)


READINGS = {
    ATTENDANCE: reading(),
    NO_WATER: reading(type="water", hotel="دار المنارة", location_kind="room", number_words="318", location_number="318"),
    SICK: reading(
        type="health", hotel="دار المنارة", location_kind="room", number_words="220", location_number="220",
        pilgrim_name="زكريا",
    ),
    LEAK_PHOTO: reading(type="water"),
    FOUND_IT: reading(),
}


def read(text, photo_attached=False):
    return build_report(text, READINGS[text], photo_attached=photo_attached)


def group(*texts, photo_on=None):
    return [
        {"sender": f"موظف {i}", "time": f"8:{i:02d}", "text": text, "photo": "ماسورة" if text == photo_on else None}
        for i, text in enumerate(texts, start=1)
    ]


def test_reports_become_cases_and_the_rest_is_counted_but_not_shown():
    scene = build_scene(group(ATTENDANCE, NO_WATER, FOUND_IT), read)
    assert [case["type"] for case in scene["cases"]] == [copy.TYPES["water"]]
    assert scene["not_reports"] == 2
    assert [message["text"] for message in scene["messages"]] == [ATTENDANCE, NO_WATER, FOUND_IT]


def test_the_cases_are_in_board_order_with_the_most_urgent_first():
    scene = build_scene(group(NO_WATER, SICK), read)
    assert [case["priority"] for case in scene["cases"]] == ["critical", "urgent"]


def test_a_found_it_reply_closes_nothing():
    scene = build_scene(group(NO_WATER, FOUND_IT), read)
    assert all(case["state"] != "closed" for case in scene["cases"])


def test_a_report_that_lacks_its_place_shows_the_one_question_the_sender_was_asked():
    scene = build_scene(group(LEAK_PHOTO, photo_on=LEAK_PHOTO), read)
    (case,) = scene["cases"]
    assert case["question"] == "ما رقم الغرفة أو الدور؟"
    assert case["photo"] is True


def test_a_complete_report_was_asked_nothing():
    (case,) = build_scene(group(NO_WATER), read)["cases"]
    assert case["question"] is None


def test_the_rasd_side_never_shows_a_full_name_or_the_words_of_a_message():
    scene = build_scene(group(SICK), read)
    shown = json.dumps(scene["cases"], ensure_ascii=False)
    assert "زكريا" not in shown and "تعبان" not in shown
    assert scene["cases"][0]["label"] == "ز · بلاغ 1"


def test_the_invented_group_mixes_what_the_owner_asked_for():
    """Attendance, a gift complaint, a pipe photo and a 'found it' reply, in one group."""
    group_file = json.loads(Path(GROUP_FILE).read_text(encoding="utf-8"))
    texts = " | ".join(message["text"] for message in group_file["messages"])
    assert "الحضور" in texts and "هدي" in texts and "لقيناها 👍" in texts
    assert any(message["photo"] for message in group_file["messages"])
