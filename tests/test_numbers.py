"""The dialect number parser: spoken Arabic number words -> digits.

The numbers used here are made up for these tests. They are deliberately not the
room numbers of the benchmark reports, so the benchmark stays an honest check.
"""

import pytest

from rasd.numbers import (
    HUNDRED_ENDINGS,
    TEEN_ENDINGS,
    contains_name,
    contains_number,
    contains_words,
    contains_words_in_order,
    hundred_spellings,
    normalise,
    spoken_number,
    teen_spellings,
)


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


# --- a number written in digits in the message ------------------------------


def test_a_number_written_in_western_digits_is_found():
    assert contains_number("ما في موية في غرفة 907 من الصبح", "907") is True


def test_a_number_written_in_arabic_digits_is_found():
    assert contains_number("ما في موية في غرفة ٩٠٧ من الصبح", "907") is True


def test_a_number_written_in_urdu_digits_is_found():
    assert contains_number("کمرہ نمبر ۹۰۷ میں پانی نہیں ہے", "907") is True


def test_a_number_that_is_only_part_of_a_longer_number_is_not_found():
    assert contains_number("ما في موية في غرفة 1907", "907") is False
    assert contains_number("ما في موية في غرفة 9075", "907") is False


def test_a_number_with_extra_zeros_in_front_is_a_different_number():
    assert contains_number("غرفة 0907", "907") is False


def test_the_right_number_is_found_among_several():
    assert contains_number("3 شنط ناقصة من غرفة 907 والدور 9", "907") is True
    assert contains_number("3 شنط ناقصة من غرفة 907 والدور 9", "355") is False


def test_digits_glued_to_a_word_are_still_found():
    assert contains_number("ما في موية بغرفة907", "907") is True


def test_a_message_with_no_digits_contains_no_number():
    assert contains_number("ما في موية في غرفة تسعمية وسبعة", "907") is False


def test_an_empty_number_is_never_found():
    assert contains_number("غرفة 907", "") is False


# --- the dialect words for 11 to 19, as a list the prompt can show ----------


def test_teen_spellings_cover_every_number_from_11_to_19():
    spellings = teen_spellings()
    assert sorted(spellings) == list(range(11, 20))
    assert all(spellings[number] for number in spellings)


def test_teen_spellings_are_whole_words_with_the_commonest_ending():
    assert "خمسطعش" in teen_spellings()[15]
    assert "طنعش" in teen_spellings()[12]
    assert all(word.endswith(TEEN_ENDINGS[0]) for words in teen_spellings().values() for word in words)


def test_no_word_is_listed_under_two_numbers():
    words = [word for spellings in teen_spellings().values() for word in spellings]
    assert len(words) == len(set(words))


def test_the_parser_reads_every_listed_spelling_with_every_ending():
    for number, spellings in teen_spellings().items():
        for word in spellings:
            beginning = word.removesuffix(TEEN_ENDINGS[0])
            for ending in TEEN_ENDINGS:
                assert spoken_number(beginning + ending) == str(number), beginning + ending


# --- the dialect words for the hundreds, as a list the prompt can show -------


def test_hundred_spellings_cover_one_hundred_to_nine_hundred():
    spellings = hundred_spellings()
    assert sorted(spellings) == [100, 200, 300, 400, 500, 600, 700, 800, 900]
    assert all(spellings[number] for number in spellings)


def test_hundred_spellings_are_written_the_way_people_write_them():
    assert "ستمية" in hundred_spellings()[600]
    assert "مية" in hundred_spellings()[100]
    assert "ميتين" in hundred_spellings()[200]


def test_no_hundred_word_is_listed_under_two_numbers():
    words = [word for spellings in hundred_spellings().values() for word in spellings]
    assert len(words) == len(set(words))


def test_the_parser_reads_every_listed_hundred_as_its_number():
    for number, spellings in hundred_spellings().items():
        for word in spellings:
            assert spoken_number(word) == str(number), word


def test_the_parser_reads_the_hundreds_from_300_with_every_ending():
    for number, spellings in hundred_spellings().items():
        if number < 300:
            continue
        for word in spellings:
            beginning = normalise(word).removesuffix(HUNDRED_ENDINGS[0])
            for ending in HUNDRED_ENDINGS:
                assert spoken_number(beginning + ending) == str(number), beginning + ending


# --- words quoted from two parts of a message ----------------------------------

SMOKE = "في دخان طالع من المطبخ في الدور التاسع، وصوت إنذار"


def test_words_from_two_parts_of_a_message_are_found_in_order():
    assert contains_words_in_order(SMOKE, "دخان طالع من المطبخ وصوت إنذار") is True


def test_one_continuous_piece_is_found_too():
    assert contains_words_in_order(SMOKE, "دخان طالع من المطبخ") is True


def test_punctuation_and_a_glued_and_do_not_matter():
    assert contains_words_in_order(SMOKE, "دخان طالع، صوت إنذار") is True


def test_a_word_that_is_not_in_the_message_is_not_found():
    assert contains_words_in_order(SMOKE, "دخان طالع من الغرفة") is False


def test_words_in_the_wrong_order_are_not_found():
    assert contains_words_in_order(SMOKE, "صوت إنذار دخان طالع") is False


def test_a_word_cannot_be_used_twice():
    assert contains_words_in_order(SMOKE, "دخان دخان") is False


def test_empty_words_are_never_found():
    assert contains_words_in_order(SMOKE, "") is False
    assert contains_words_in_order(SMOKE, " ، ") is False


# --- a name with a short word glued to its front ("بدار المنارة") --------------------


@pytest.mark.parametrize("written", ["بدار المنارة", "لدار المنارة", "وبدار المنارة", "فلدار المنارة", "كدار المنارة", "ودار المنارة"])
def test_a_name_is_found_when_a_short_word_is_glued_to_its_front(written):
    assert contains_name(f"الموية مقطوعة {written} من الصبح", "دار المنارة")


def test_a_name_that_starts_with_the_article_is_found_after_a_glued_lam():
    assert contains_name("وصّلوه للمنارة بعد العصر", "المنارة")
    assert contains_name("هو ساكن بالمنارة", "المنارة")


def test_a_name_is_still_found_when_nothing_is_glued_to_it():
    assert contains_name("الموية مقطوعة في دار المنارة", "دار المنارة")


@pytest.mark.parametrize("written", ["قدار المنارة", "بدارين المنارة", "بدار", "المنارة بدار"])
def test_a_glued_word_does_not_make_other_words_match(written):
    assert not contains_name(f"الموية مقطوعة {written} من الصبح", "دار المنارة")


def test_an_empty_name_is_never_found():
    assert not contains_name("الموية مقطوعة بدار المنارة", "")
