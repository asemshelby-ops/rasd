"""Reading the MOCK Nusuk card of the demo scene with Claude vision.

    reading = read_mock_card(image_bytes, "image/png", client)

This is the one place where a photo is analysed, and the one place where a visa
number reaches the model. It exists for the demo scene only, so it is fenced in:

  - The card must visibly be marked as a specimen ("نموذج تجريبي" / "SPECIMEN").
    A card without that mark is refused and nothing is read from it.
  - Nothing is stored here. The caller keeps the visa number in its private
    place and never shows it.

No digital scan (QR code, chip) is read: only what is printed on the card.
"""

import base64

import anthropic
import pydantic

from rasd.understand import DEFAULT_MODEL

CARD_PROMPT = """\
This is a photo of a card used in a software demonstration.

is_marked_as_specimen - true only if the card itself visibly carries the words \
SPECIMEN or نموذج تجريبي, which mark it as a mock card that is not real.

If it is marked as a specimen, copy from the card:
full_name - the holder's name, exactly as printed in Latin letters
visa_number - the visa number, digits only

If it is not marked as a specimen, answer false and leave both fields empty. \
Do not read anything else from the card."""


class CardReading(pydantic.BaseModel):
    is_marked_as_specimen: bool
    full_name: str
    visa_number: str = pydantic.Field(repr=False)  # never printed


def read_mock_card(
    image: bytes, media_type: str, client: anthropic.Anthropic, model: str = DEFAULT_MODEL
) -> CardReading | None:
    """What is printed on a mock card, or None when the card is not a marked mock or the call failed."""
    try:
        reply = client.messages.parse(
            model=model,
            max_tokens=1000,
            system=CARD_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": base64.standard_b64encode(image).decode("ascii"),
                            },
                        },
                        {"type": "text", "text": "Read this card."},
                    ],
                }
            ],
            output_format=CardReading,
            output_config={"effort": "low"},
        )
    except (anthropic.APIError, pydantic.ValidationError):
        return None
    reading = reply.parsed_output
    if reading is None or not reading.is_marked_as_specimen or not reading.full_name.strip():
        return None
    return reading
