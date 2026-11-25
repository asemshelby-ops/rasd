"""Passport and visa numbers never go to the AI model.

    safe_text, private = redact(message)

redact() finds those numbers with plain rules (no AI), replaces each with a
placeholder such as "[رقم جواز]", and returns the real values separately. It
also rewrites Arabic and Urdu digits as 0-9.

Only safe_text is sent to the model, printed, or shown on a screen. The real
values are for the pilgrim-affairs record only: keep them in their own place,
never in a log, never on the big screen. Printing a PrivateNumbers object shows
how many numbers it holds, not the numbers.
"""

import re
from dataclasses import dataclass

from rasd.text import to_western_digits

PASSPORT_MARK = "[رقم جواز]"
VISA_MARK = "[رقم تأشيرة]"
OTHER_MARK = "[رقم محجوب]"

# The word before the number, in Arabic, English and Urdu.
_PASSPORT_LABEL = r"(?:(?:ال)?جواز\w*|باسبور\w*|passport|پاسپورٹ)"
_VISA_LABEL = r"(?:(?:ال)?ت[أا]شير[ةه]\w*|فيز[اةه]|visa|ویز[اہ])"
# What may stand between the word and the number: "السفر", "رقم", "رقمه", "No", ":", "#", "-".
_FILLER = r"(?:(?:ال)?سفر\w*|رقم\w*|no|number|num|نمبر|هو|is)"
_BETWEEN = rf"[\s:#\-–=.]*(?:{_FILLER}[\s:#\-–=.]*){{0,2}}"
# A number as people write it: digits that may be split by single spaces or dashes ("1234 5678").
_SPLIT_DIGITS = r"[0-9](?:[ \-]?[0-9]){4,13}"
# After the word "passport": letters and digits mixed ("P12AB345"), or a letter, a space and digits ("A 1234567").
_PASSPORT_NUMBER = rf"(?:[A-Za-z]{{0,3}}[ \-]?{_SPLIT_DIGITS}|(?=[A-Za-z0-9]*[0-9]{{2}})[A-Za-z0-9]{{6,12}})"

_LABELLED_PASSPORT = re.compile(rf"({_PASSPORT_LABEL}{_BETWEEN})({_PASSPORT_NUMBER})", re.IGNORECASE)
_LABELLED_VISA = re.compile(rf"({_VISA_LABEL}{_BETWEEN})({_SPLIT_DIGITS})", re.IGNORECASE)
# One or two letters and then 6 to 9 digits looks like a passport number even without a label.
_PASSPORT_SHAPE = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]{1,2}[0-9]{6,9}(?![A-Za-z0-9])")
# A mobile number written in groups: "055 123 4567", "+966 55 123 4567".
_PHONE = re.compile(r"(?<![0-9])(?:\+|00)?(?:966[ \-]?|0)5[0-9](?:[ \-]?[0-9]){7}(?![0-9])")
# Nine digits or more is never a room: a phone, an ID or a visa number.
_LONG_NUMBER = re.compile(r"(?<![0-9])[0-9]{9,}(?![0-9])")


@dataclass(frozen=True)
class PrivateNumbers:
    """The real numbers taken out of one message. Never print the values."""

    passport: tuple[str, ...] = ()
    visa: tuple[str, ...] = ()
    other: tuple[str, ...] = ()

    def __repr__(self) -> str:
        return f"PrivateNumbers(passport: {len(self.passport)}, visa: {len(self.visa)}, other: {len(self.other)})"


def redact(message: str) -> tuple[str, PrivateNumbers]:
    """Returns the message without passport, visa and other long numbers, and those numbers apart."""
    found = {"passport": [], "visa": [], "other": []}

    def after_label(kind: str, mark: str):
        def replace(match):
            found[kind].append(match.group(2))
            return match.group(1) + mark

        return replace

    def whole(kind: str, mark: str):
        def replace(match):
            found[kind].append(match.group(0))
            return mark

        return replace

    text = to_western_digits(message)
    text = _LABELLED_PASSPORT.sub(after_label("passport", PASSPORT_MARK), text)
    text = _LABELLED_VISA.sub(after_label("visa", VISA_MARK), text)
    text = _PASSPORT_SHAPE.sub(whole("passport", PASSPORT_MARK), text)
    text = _PHONE.sub(whole("other", OTHER_MARK), text)
    text = _LONG_NUMBER.sub(whole("other", OTHER_MARK), text)
    return text, PrivateNumbers(tuple(found["passport"]), tuple(found["visa"]), tuple(found["other"]))
