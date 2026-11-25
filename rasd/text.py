"""Small text helpers shared by the rest of the project."""

# Arabic-Indic digits (٠-٩) and the Urdu/Persian forms (۰-۹), mapped to 0-9.
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def to_western_digits(text: str) -> str:
    """Rewrite any Arabic or Urdu digits as 0-9 and leave everything else alone."""
    return text.translate(_DIGITS)

# Urdu letters that look like Arabic ones, mapped to the Arabic letter.
_URDU_LETTERS = str.maketrans({"ک": "ك", "ی": "ي", "ہ": "ه", "ھ": "ه", "ے": "ي"})


def arabic_letters(text: str) -> str:
    """Rewrite Urdu forms of letters as the Arabic ones, so that one name has one spelling."""
    return text.translate(_URDU_LETTERS)

# Letters Urdu writes and Arabic does not. Gulf Arabic borrows a few others (گ چ پ), so those do not count.
_URDU_ONLY = set("ٹڈڑںےہھۓ")
_URDU_FORMS = set("کی")


def language_of(text: str) -> str | None:
    """The language a message is written in, told by its letters: "ar", "ur", "en", or None.

    It is only used to label a report on the board (two chips when two reports merge).
    """
    letters = [character for character in text if character.isalpha()]
    if not letters:
        return None
    arabic_script = [c for c in letters if "\u0600" <= c <= "\u06ff" or "\u0750" <= c <= "\u077f"]
    if len(arabic_script) * 2 < len(letters):
        return "en" if any("a" <= c.lower() <= "z" for c in letters) else None
    urdu_only = sum(1 for c in arabic_script if c in _URDU_ONLY)
    urdu_forms = sum(1 for c in arabic_script if c in _URDU_FORMS)
    return "ur" if urdu_only >= 2 or (urdu_only >= 1 and urdu_forms >= 1) else "ar"
