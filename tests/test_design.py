"""The design pass on the two screens the judges see: the board and the phone report page.

Only the logic behind the new layout is tested here; how it looks is checked by eye
in screenshots/design/. No AI model and no network. Everything is invented.
"""

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app import copy
from app.main import create_app
from demo import scene
from rasd.elm import SimulatedElm
from rasd.text import language_of
from rasd.understand import Reading, build_report

HOTEL = "برج السكينة"


def reading(**fields) -> Reading:
    base = dict(
        type="water", hotel="", location_kind="room", number_words="907", location_number="907", pilgrim_name="",
        risks=[], partial_words="", confidence="high",
    )  # fmt: skip
    base.update(fields)
    return Reading(**base)


LOST = dict(type="lost_pilgrim", location_kind="none", number_words="", location_number="")


class Engine:
    def __init__(self):
        self.elm, self.readings = SimulatedElm(), {}

    def read(self, text, photo_attached=False):
        return build_report(text, self.readings.get(text, reading()), photo_attached=photo_attached)


class Clock:
    def __init__(self):
        self.now = datetime(2026, 12, 23, 10, 0, 0)

    def __call__(self):
        return self.now


@pytest.fixture
def site(tmp_path):
    engine, clock = Engine(), Clock()
    client = TestClient(create_app(engine=engine, db_path=tmp_path / "rasd.db", now=clock))
    client.engine, client.clock = engine, clock
    return client


def send(site, text, hotel=HOTEL):
    return site.post("/api/reports", data={"text": text, "hotel": hotel}).json()


def board(site):
    return site.get("/api/board").json()


# --- which language a message is in (for the two chips of the merge moment) ---------------------------


@pytest.mark.parametrize(
    "text, language",
    [
        ("المكيف خربان في غرفة 907", "ar"),
        ("میرا نام زاہد کریم ہے۔ میں راستہ بھول گیا ہوں", "ur"),
        ("AC not working in room 204", "en"),
        ("الگاراج فيه چاي", "ar"),  # Gulf spelling uses a few of these letters; that does not make it Urdu
        ("907", None),
        ("", None),
        ("👍", None),
    ],
)
def test_the_language_of_a_message_is_told_by_its_letters(text, language):
    assert language_of(text) == language


def test_the_two_notes_of_the_scene_are_arabic_and_urdu():
    assert (language_of(scene.COUNTER_NOTE), language_of(scene.PILGRIM_NOTE)) == ("ar", "ur")


# --- the merge moment: a stamp and the languages of the reports ----------------------------------------


def merged_scene(site):
    site.engine.readings[scene.COUNTER_NOTE] = reading(**LOST)
    site.engine.readings[scene.PILGRIM_NOTE] = reading(**LOST)
    send(site, scene.COUNTER_NOTE)
    send(site, scene.PILGRIM_NOTE)


def test_a_merged_case_names_the_languages_of_its_reports(site):
    merged_scene(site)
    (case,) = board(site)["cases"]
    assert case["languages"] == ["العربية", "الأردية"]
    page = site.get("/board").text
    assert 'class="stamp"' in page and "بلاغان، حالة واحدة" in page
    assert page.count('class="language-chip"') == 2 and "الأردية" in page


def test_a_case_of_one_report_has_no_stamp_and_two_arabic_reports_show_one_chip(site):
    send(site, "ما في موية في غرفة 907")
    assert 'class="stamp"' not in site.get("/board").text
    send(site, "ما في موية في غرفة 907")
    assert board(site)["cases"][0]["languages"] == ["العربية"]
    assert site.get("/board").text.count('class="language-chip"') == 1


def test_the_card_carries_its_report_count_so_the_script_can_see_a_merge(site):
    merged_scene(site)
    assert 'data-count="2"' in site.get("/board/fragment").text


# --- the header: three counts ----------------------------------------------------------------------------


def test_the_header_counts_open_critical_and_closed_today(site):
    site.engine.readings["حاج تايه"] = reading(**LOST)
    send(site, "حاج تايه")  # critical
    send(site, "ما في موية في غرفة 907")  # urgent
    site.engine.readings["الشنط ما وصلت غرفة 330"] = reading(type="luggage", number_words="330", location_number="330")
    send(site, "الشنط ما وصلت غرفة 330")
    site.post("/api/cases/3/close", data={"who": "سالم"})
    assert board(site)["counts"] == {"open": 2, "critical": 1, "closed_today": 1}
    page = site.get("/board").text
    for label in (copy.COUNT_OPEN, copy.COUNT_CRITICAL, copy.COUNT_CLOSED_TODAY):
        assert label in page


def test_a_case_closed_yesterday_is_not_closed_today(site):
    send(site, "ما في موية في غرفة 907")
    site.post("/api/cases/1/close", data={"who": "سالم"})
    site.clock.now += timedelta(days=1)
    assert board(site)["counts"]["closed_today"] == 0


# --- the layout: a band for critical cases, then now, overdue, closed -------------------------------------


def sections(site):
    return {name: [case["id"] for case in found] for name, found in board(site)["sections"].items()}


def test_open_critical_cases_are_in_the_band_and_the_rest_in_three_columns(site):
    site.engine.readings["حاج تايه"] = reading(**LOST)
    send(site, "حاج تايه")  # 1: critical
    send(site, "ما في موية في غرفة 907")  # 2: urgent, routed
    site.engine.readings["في مشكلة"] = reading(type="unclear", location_kind="none", number_words="", location_number="")
    send(site, "في مشكلة")  # 3: waiting for the supervisor: still "now"
    site.engine.readings["الشنط ما وصلت غرفة 330"] = reading(type="luggage", number_words="330", location_number="330")
    send(site, "الشنط ما وصلت غرفة 330")  # 4
    site.post("/api/cases/4/close", data={"who": "سالم"})
    assert sections(site) == {"critical": [1], "now": [2, 3], "late": [], "closed": [4]}
    site.clock.now += timedelta(minutes=16)
    assert sections(site) == {"critical": [1], "now": [], "late": [2, 3], "closed": [4]}  # an overdue critical case stays in the band


def test_a_closed_critical_case_leaves_the_band(site):
    site.engine.readings["حاج تايه"] = reading(**LOST)
    send(site, "حاج تايه")
    site.post("/api/cases/1/close", data={"who": "سالم"})
    assert sections(site) == {"critical": [], "now": [], "late": [], "closed": [1]}


def test_the_board_page_has_the_band_the_three_columns_and_a_short_line_for_an_empty_one(site):
    page = site.get("/board").text
    assert 'id="critical-band"' in page
    for title in copy.SECTIONS.values():
        assert title in page
    assert page.count(copy.NO_CASES) == 3 and 'class="empty"' in page


def test_the_board_no_longer_holds_the_name_box_or_the_size_buttons(site):
    page = site.get("/board").text
    assert 'id="who"' not in page and copy.LARGER not in page and copy.SMALLER not in page
    assert 'aria-label="صفحات رصد"' not in page  # the header is the name, the time and the counts only
    assert 'id="clock"' in page


def test_the_replay_notice_is_a_small_corner_label(site):
    site.post("/api/operator/mode", data={"mode": "replay"})
    page = site.get("/board").text
    assert 'class="replay-corner"' in page and copy.REPLAY_MODE_ON in page
    assert "replay-banner" not in page


# --- the name and the type size moved to the operator page -------------------------------------------------


def test_the_operator_page_holds_the_name_and_the_size_buttons(site):
    page = site.get("/operator").text
    assert copy.YOUR_NAME in page and copy.LARGER in page and copy.SMALLER in page


def test_the_name_given_on_the_operator_page_signs_the_actions_on_the_board(site):
    send(site, "ما في موية في غرفة 907")
    refused = site.post("/api/cases/1/close")
    assert refused.status_code == 400 and refused.json()["message"] == copy.NAME_NEEDED
    site.post("/operator/board-name", data={"name": "  هشام "}, follow_redirects=False)
    assert site.post("/api/cases/1/close").status_code == 200
    (case,) = board(site)["cases"]
    assert case["closed_by"] == "هشام"
    assert "هشام" in site.get("/operator").text  # the page shows whose name signs


def test_a_name_sent_with_the_action_still_wins(site):
    send(site, "ما في موية في غرفة 907")
    site.post("/operator/board-name", data={"name": "هشام"})
    site.post("/api/cases/1/close", data={"who": "سالم"})
    assert board(site)["cases"][0]["closed_by"] == "سالم"


def test_the_size_set_on_the_operator_page_reaches_the_board_and_has_limits(site):
    assert board(site)["scale"] == 1.0
    site.post("/operator/board-size", data={"change": "larger"})
    site.post("/operator/board-size", data={"change": "larger"})
    assert board(site)["scale"] == 1.2
    assert 'data-scale="1.2"' in site.get("/board/fragment").text
    for _ in range(30):
        site.post("/operator/board-size", data={"change": "smaller"})
    assert board(site)["scale"] == 0.7
    for _ in range(30):
        site.post("/operator/board-size", data={"change": "larger"})
    assert board(site)["scale"] == 2.0


# --- the phone page and the shared look ------------------------------------------------------------------------


def test_the_phone_page_is_a_chat_with_the_hotel_on_top_and_a_round_record_button(site):
    page = site.get("/report").text
    assert copy.PROTOTYPE_LABEL in page
    assert page.index('id="hotel"') < page.index('id="chat"') < page.index('id="text"')
    assert 'id="record"' in page and "record-main" in page
    assert f'aria-label="{copy.RECORD}"' in page


def test_one_font_family_and_it_is_served_from_the_laptop(site):
    css = site.get("/static/style.css").text
    assert "IBM Plex Sans Arabic" in css
    for other in ("Segoe UI", "Tahoma", "Noto Kufi", "Arial", "Geeza"):
        assert other not in css
    assert "fonts.googleapis" not in css and "http" not in css  # works with no internet
    assert site.get("/static/fonts/ibm-plex-sans-arabic-arabic-400-normal.woff2").status_code == 200


def test_the_colours_of_the_brief_are_the_only_meaning_colours(site):
    css = site.get("/static/style.css").text.upper()
    for token in ("#EEF2F1", "#FFFFFF", "#10202B", "#4A5A66", "#D5DDDB", "#B3261E", "#B26A00", "#1F6F78", "#5B6770", "#0B6E4F"):
        assert token in css, token
    assert "PREFERS-REDUCED-MOTION" in css


# --- the owner's review of the design (three changes) ---------------------------------------------------


def test_the_priority_border_is_on_the_start_side_with_logical_css(site):
    css = site.get("/static/style.css").text
    assert "border-inline-start" in css and "border-left" not in css


def test_the_record_button_is_the_only_main_action_on_the_phone_page(site):
    page = site.get("/report").text
    assert page.count("record-main") == 1 and 'class="primary"' not in page


def test_the_attachments_are_behind_one_small_plus_button(site):
    page = site.get("/report").text
    more = page[page.index('<details class="more"') : page.index("</details>")]
    assert f'aria-label="{copy.MORE_ATTACHMENTS}"' in more and ">+<" in more
    for control in ('id="audio-file"', 'id="pilgrim-photo"'):
        assert control in more
    assert "<details class=\"more\" id=\"more\">" in page  # no "open": it starts closed
    assert page.index('id="text"') < page.index('id="record"')  # the text box is the second option, above the record button


def test_the_plus_menu_is_never_opened_by_the_page_itself(site):
    assert ".open = true" not in site.get("/static/report.js").text


def test_the_mock_card_is_one_suggestion_button_above_the_text_box_hidden_until_it_is_possible(site):
    page = site.get("/report").text
    more = page[page.index('<details class="more"') : page.index("</details>")]
    assert 'id="card-photo"' not in more
    button = page[page.index('id="card-button"') - 80 : page.index('id="card-photo"') + 120]
    assert "suggestion" in button and " hidden>" in button and copy.SHOW_CARD in button
    assert 'capture="environment"' in button  # it opens the camera directly
    assert page.index('id="chat"') < page.index('id="card-button"') < page.index('id="text"')

