"""What may be shown on the big screen about a pilgrim: the first letter of the name and the report number."""

from rasd.display import screen_label


def test_only_the_first_letter_of_the_name_and_the_report_number_are_shown():
    label = screen_label(17, "نبيل سعد الدين")
    assert label == "ن · بلاغ 17"
    assert "نبيل" not in label and "سعد" not in label


def test_a_title_before_the_name_is_skipped():
    assert screen_label(4, "الحاج منصور خليل") == "م · بلاغ 4"
    assert screen_label(4, "الحاجة زينب عمر") == "ز · بلاغ 4"


def test_a_latin_name_gives_its_first_letter_in_capitals():
    assert screen_label(9, "yusuf khan") == "Y · بلاغ 9"


def test_a_report_without_a_name_shows_only_its_number():
    assert screen_label(23, None) == "بلاغ 23"
    assert screen_label(23, "  ") == "بلاغ 23"


def test_marks_and_digits_before_the_name_are_skipped():
    assert screen_label(5, "- 1) سليم ناصر") == "س · بلاغ 5"
