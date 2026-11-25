"""Small text helpers shared by the rest of the project."""

# Arabic-Indic digits (٠-٩) and the Urdu/Persian forms (۰-۹), mapped to 0-9.
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def to_western_digits(text: str) -> str:
    """Rewrite any Arabic or Urdu digits as 0-9 and leave everything else alone."""
    return text.translate(_DIGITS)
