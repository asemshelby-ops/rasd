"""What may be shown where everybody can see it.

The big screen never shows a pilgrim's full name: only the first letter of the
name and the report number. Photos are never shown there either.
"""

_TITLES = {"الحاج", "الحاجة", "الحاجه", "حاج", "حاجة", "حاجه", "السيد", "السيدة", "السيده", "الاخ", "الأخ", "الاخت", "الأخت"}


def screen_label(report_number: int, pilgrim_name: str | None) -> str:
    """The label of a report on the big screen: "ن · بلاغ 17", or "بلاغ 17" when there is no name."""
    words = [word for word in (pilgrim_name or "").split() if word not in _TITLES]
    letters = [character for word in words for character in word if character.isalpha()]
    if not letters:
        return f"بلاغ {report_number}"
    return f"{letters[0].upper()} · بلاغ {report_number}"
