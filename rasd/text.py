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
