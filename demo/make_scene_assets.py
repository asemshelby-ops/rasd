"""Writes the saved files of the demo scene into demo/scene/.

    python -m demo.make_scene_assets

It writes three things:
  mock_card.png            a card that is plainly a MOCK (it says so across its face)
  01_counter_arabic.wav    PLACEHOLDER sound for the counter employee's voice note
  02_pilgrim_urdu.wav      PLACEHOLDER sound for the pilgrim's voice note
  transcripts.json         the words of each voice note, used when the scene is replayed

The two sound files are plain tones, not speech: the team records the real voice
notes and puts them in their place (keep the file names, or change them in
transcripts.json too). Everything here is invented: the person, the visa number
(it starts with 999000), the hotels. Drawing the card needs Pillow
(pip install pillow); nothing else in the project does.
"""

import json
import math
import struct
import wave
from pathlib import Path

from demo.scene import (  # noqa: F401  (the scene's own words and file names)
    CARD_FILE,
    CARD_MARKS,
    CARD_NAME,
    CARD_VISA,
    COUNTER_FILE,
    COUNTER_NOTE,
    PILGRIM_FILE,
    PILGRIM_NOTE,
    REPORTING_HOTEL,
    SCENE_DIR,
)

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"  # on Windows: C:/Windows/Fonts/tahomabd.ttf


def write_placeholder_tone(path: Path, pitch: float, seconds: float = 2.0, rate: int = 16000) -> None:
    """A plain tone, so that the file is a real sound file. It is NOT speech."""
    frames = b"".join(
        struct.pack("<h", int(9000 * math.sin(2 * math.pi * pitch * n / rate))) for n in range(int(seconds * rate))
    )
    with wave.open(str(path), "wb") as sound:
        sound.setnchannels(1)
        sound.setsampwidth(2)
        sound.setframerate(rate)
        sound.writeframes(frames)


def draw_mock_card(path: Path, font_file: str = FONT) -> None:
    """Draws the mock card. It copies no real card: no emblem, no logo, and SPECIMEN across its face."""
    from PIL import Image, ImageDraw, ImageFont

    def font(size):
        return ImageFont.truetype(font_file, size, layout_engine=ImageFont.Layout.RAQM)

    def arabic(draw, xy, text, size, fill, anchor="ra"):
        draw.text(xy, text, font=font(size), fill=fill, direction="rtl", language="ar", anchor=anchor)

    width, height = 1200, 760
    card = Image.new("RGB", (width, height), "#f3efe2")
    draw = ImageDraw.Draw(card)
    for x in range(-height, width, 48):  # light hatching, so the card looks like nothing official
        draw.line([(x, height), (x + height, 0)], fill="#e2dcc8", width=6)
    draw.rectangle([0, 0, width, 140], fill="#2b2f36")
    arabic(draw, (width - 40, 20), "بطاقة تجريبية لعرض «رصد»", 40, "#ffffff")
    draw.text((40, 30), "MOCK CARD · RASD DEMO", font=font(28), fill="#ffffff")
    arabic(draw, (width - 40, 82), "ليست بطاقة نسك حقيقية", 30, "#ffd28a")
    draw.text((40, 88), "NOT A REAL NUSUK CARD", font=font(26), fill="#ffd28a")

    # The two fields the scene reads, on the left, clear of the stamp.
    draw.text((60, 185), "Name", font=font(30), fill="#555555")
    arabic(draw, (170, 180), "الاسم", 30, "#555555", anchor="la")
    draw.text((60, 228), CARD_NAME, font=font(66), fill="#111111")
    draw.text((60, 350), "Visa No.", font=font(30), fill="#555555")
    arabic(draw, (210, 345), "رقم التأشيرة", 30, "#555555", anchor="la")
    draw.text((60, 393), CARD_VISA, font=font(66), fill="#111111")
    draw.text((60, 540), "FICTIONAL PERSON · INVENTED NUMBER", font=font(26), fill="#333333")
    arabic(draw, (width - 60, 532), "شخص خيالي ورقم مخترع", 32, "#333333")

    # The mark the reader looks for: a large red stamp on the right, and a band along the bottom.
    red = (190, 20, 20, 255)
    stamp = Image.new("RGBA", (500, 250), (0, 0, 0, 0))
    stamp_draw = ImageDraw.Draw(stamp)
    stamp_draw.rectangle([5, 5, 494, 244], outline=red, width=10)
    stamp_draw.text((250, 80), "SPECIMEN", font=font(82), fill=red, anchor="mm")
    stamp_draw.text((250, 178), "نموذج تجريبي", font=font(64), fill=red, anchor="mm", direction="rtl", language="ar")
    stamp = stamp.rotate(7, expand=True, resample=Image.Resampling.BICUBIC)
    card.paste(stamp, (width - stamp.width - 30, 190), stamp)
    draw.rectangle([0, height - 110, width, height], fill="#be1414")
    draw.text((40, height - 82), "SPECIMEN · SPECIMEN", font=font(44), fill="#ffffff")
    arabic(draw, (width - 40, height - 92), "نموذج تجريبي", 50, "#ffffff")
    card.save(path, optimize=True)


def main() -> None:
    SCENE_DIR.mkdir(parents=True, exist_ok=True)
    write_placeholder_tone(SCENE_DIR / COUNTER_FILE, pitch=440.0)
    write_placeholder_tone(SCENE_DIR / PILGRIM_FILE, pitch=330.0)
    listed = {
        "note": "Words of the saved voice notes. The sound files are PLACEHOLDER tones until the team records them.",
        "voice_notes": {COUNTER_FILE: COUNTER_NOTE, PILGRIM_FILE: PILGRIM_NOTE},
    }
    (SCENE_DIR / "transcripts.json").write_text(json.dumps(listed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    draw_mock_card(SCENE_DIR / CARD_FILE)
    print(f"Wrote the scene files to {SCENE_DIR}")


if __name__ == "__main__":
    main()
