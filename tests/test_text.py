from rasd.text import to_western_digits


def test_arabic_indic_digits_become_western():
    assert to_western_digits("غرفة ٤١٢") == "غرفة 412"


def test_urdu_and_persian_digits_become_western():
    assert to_western_digits("کمرہ ۷۲۶") == "کمرہ 726"


def test_western_digits_are_left_alone():
    assert to_western_digits("غرفة 509") == "غرفة 509"
