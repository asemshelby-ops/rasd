"""The dialect number parser: spoken Arabic number words -> digits.

The numbers used here are made up for these tests. They are deliberately not the
room numbers of the benchmark reports, so the benchmark stays an honest check.
"""

import pytest

from rasd.numbers import contains_words, spoken_number


@pytest.mark.parametrize(
    "words, digits",
    [
        ("تسعمية وسبعة", "907"),
        ("ستمية وطنعش", "612"),
        ("ميتين وأربعطعش", "214"),
        ("خمسمية وتسعة وأربعين", "549"),
        ("سبعمية وثلاثين", "730"),
        ("مية وخمسة", "105"),
    ],
)
def test_hundreds_joined_with_and(words, digits):
    assert spoken_number(words) == digits


@pytest.mark.parametrize(
    "words, digits",
    [
        ("ألف وميتين وستة", "1206"),
        ("ألف وسبعطعش", "1017"),
        ("ألف وتسعمية وخمسة", "1905"),
        ("ألفين وثلاثمية وواحد", "2301"),
        ("ثلاث آلاف ومية وعشرة", "3110"),
    ],
)
def test_thousands(words, digits):
    assert spoken_number(words) == digits


@pytest.mark.parametrize(
    "words, digits",
    [
        ("ثلاثة تسعة خمسة", "395"),
        ("واحد صفر واحد سبعة", "1017"),
        ("تلاتة تسعة خمسة", "395"),
    ],
)
def test_digit_by_digit(words, digits):
    assert spoken_number(words) == digits


@pytest.mark.parametrize(
    "words, digits",
    [
        ("أحدعش صفر ثمانية", "1108"),
        ("عشرين خمسطعش", "2015"),
        ("أربعة وثلاثين صفر ستة", "3406"),
        ("تسعة خمسطعش", "915"),
    ],
)
def test_groups_said_side_by_side_are_joined(words, digits):
    assert spoken_number(words) == digits


@pytest.mark.parametrize(
    "words, digits",
    [
        ("تسعمية خمسطعش", "915"),
        ("ألف مية وستة", "1106"),
        ("خمس مية وأربعة", "504"),
    ],
)
def test_and_dropped_after_a_round_hundred_or_thousand(words, digits):
    assert spoken_number(words) == digits


@pytest.mark.parametrize(
    "words, digits",
    [
        ("ثلاثمئة وخمسة وعشرون", "325"),
        ("أربعة عشر", "14"),
        ("مائة وستة", "106"),
    ],
)
def test_standard_arabic_forms(words, digits):
    assert spoken_number(words) == digits


@pytest.mark.parametrize(
    "words, digits",
    [
        ("حدعش", "11"),
        ("اثنعشر", "12"),
        ("تلطعش", "13"),
        ("أربعتاشر", "14"),
        ("خمستعش", "15"),
        ("سطعش", "16"),
        ("سبعطعشر", "17"),
        ("ثمنطعش", "18"),
        ("تسعطعش", "19"),
    ],
)
def test_teens_in_dialect_spellings(words, digits):
    assert spoken_number(words) == digits


@pytest.mark.parametrize(
    "words, digits",
    [
        ("536", "536"),
        ("٥٣٦", "536"),
        ("۹۴۱", "941"),
    ],
)
def test_written_digits_pass_through(words, digits):
    assert spoken_number(words) == digits


@pytest.mark.parametrize(
    "words, digits",
    [
        ("الأول", "1"),
        ("السابع", "7"),
        ("التامن", "8"),
        ("العاشرة", "10"),
        ("الحادي عشر", "11"),
    ],
)
def test_ordinals_for_floors_and_elevators(words, digits):
    assert spoken_number(words) == digits


@pytest.mark.parametrize(
    "words, digits",
    [
        ("غرفة تسعمية وسبعة", "907"),
        ("غرفة رقم 536", "536"),
        ("الدور السابع", "7"),
    ],
)
def test_the_word_for_the_place_is_ignored(words, digits):
    assert spoken_number(words) == digits


@pytest.mark.parametrize(
    "words",
    [
        "",
        "فوق",
        "330، لا استنى، 303",
        "خمسة وستة",
        "ميتين وتسعمية",
        "غرفة",
    ],
)
def test_returns_none_when_it_cannot_read_one_clear_number(words):
    assert spoken_number(words) is None


def test_contains_words_ignores_spelling_details():
    message = "يا شباب الغرفة تسعمية وسبعة فيها مشكلة"
    assert contains_words(message, "تسعميه وسبعه")


def test_contains_words_matches_digits_written_in_another_script():
    assert contains_words("غرفة ٥٣٦ تحتاج مناشف", "536")


def test_contains_words_is_false_for_words_that_were_never_said():
    assert not contains_words("غرفة تسعمية وسبعة", "ستمية وطنعش")


def test_contains_words_is_false_for_an_empty_quote():
    assert not contains_words("غرفة تسعمية وسبعة", "")
