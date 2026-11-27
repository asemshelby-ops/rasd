"""The demo, end to end in a real browser: phone page, board, operator page. Replay mode only.

Run with: python -m pytest -m e2e -q
"""

import time

import pytest
from playwright.sync_api import expect

from app import copy
from demo import scene

pytestmark = pytest.mark.e2e

PHONE = (390, 844)
BIG_SCREEN = (1920, 1080)
REPORT_PAGE = f"/report?hotel={scene.REPORTING_HOTEL}"
SIGNED_BY = "مشرف التجربة"  # invented


def send_voice_note(phone, file_name):
    """The phone's own recorder file, attached with the "+": the page sends it as soon as it is chosen."""
    phone.set_input_files("#audio-file", str(scene.SCENE_DIR / file_name))


def test_a_voice_note_from_the_phone_reaches_the_board_and_is_closed_with_a_name(open_page, operator):
    operator.fill("#board-name", SIGNED_BY)
    operator.get_by_role("button", name=copy.BOARD_NAME_SAVE).click()
    expect(operator.get_by_role("status")).to_have_text(f"{copy.BOARD_NAME_NOW}: {SIGNED_BY}")

    board = open_page("/board", *BIG_SCREEN)
    phone = open_page(REPORT_PAGE, *PHONE, phone=True)
    started = time.monotonic()
    send_voice_note(phone, scene.COUNTER_FILE)
    case = board.locator("article[data-case]")
    expect(case).to_have_count(1, timeout=8000)
    assert time.monotonic() - started < 8

    case.locator('button[data-action="acknowledge"]').click()
    expect(case.get_by_text(copy.ACKNOWLEDGED, exact=True)).to_be_visible()
    case.locator('button[data-action="close"]').click()
    expect(case).to_have_attribute("data-state", "closed")
    expect(case.get_by_text(f"{copy.CLOSED_BY} {SIGNED_BY}")).to_be_visible()

    steps = phone.locator("#chat [data-steps-of] li.step")
    expect(steps).to_have_count(4)
    # The phone asks again every 3 seconds: all four reached, none left to do and none skipped.
    expect(phone.locator("#chat li.step-todo, #chat li.step-skipped")).to_have_count(0, timeout=8000)
    for key in copy.STEPS:
        expect(phone.locator(f"#chat li.step-{key}")).to_have_count(1)


def test_two_reports_of_the_same_lost_pilgrim_in_the_same_second_are_one_case_with_nothing_private_on_the_board(
    open_page, operator
):
    board = open_page("/board", *BIG_SCREEN)
    phones = [open_page(REPORT_PAGE, *PHONE, phone=True) for _ in range(2)]
    started = time.monotonic()
    send_voice_note(phones[0], scene.COUNTER_FILE)  # the counter employee, in Arabic
    send_voice_note(phones[1], scene.PILGRIM_FILE)  # the pilgrim himself, in Urdu, who says his name
    assert time.monotonic() - started < 1

    for phone in phones:  # both were answered
        expect(phone.locator("#chat li.theirs")).to_have_count(1, timeout=8000)
    case = board.locator("article[data-case]")
    expect(case).to_have_count(1, timeout=8000)
    expect(case).to_have_attribute("data-count", "2")
    expect(case.locator(".stamp")).to_contain_text(copy.count_text(2))

    shown = board.content()  # the text and the attributes, aria labels included
    name = "زاہد کریم"
    assert name in scene.PILGRIM_NOTE
    for private in (name, *name.split(), scene.CARD_NAME, *scene.CARD_NAME.split()):
        assert private not in shown, f"the board shows a name: {private}"
    for note in (scene.COUNTER_NOTE, scene.PILGRIM_NOTE):
        for words in note.replace("۔", "،").split("،"):
            if len(words.strip()) > 10:
                assert words.strip() not in shown, f"the board shows words of a message: {words.strip()}"


# For each visible piece of text on the page: its font size in pixels, and whether it is cut off sideways.
MEASURE_TEXT = """() => [...document.querySelectorAll("body *")]
  .filter(el => el.offsetParent !== null && [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim()))
  .filter(el => !el.closest(".visually-hidden"))
  .map(el => ({text: el.textContent.trim().slice(0, 30), size: parseFloat(getComputedStyle(el).fontSize),
               cut: el.scrollWidth > el.clientWidth + 1 && getComputedStyle(el).overflowX !== "visible"}))"""
SIDEWAYS_SCROLL = "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"


def test_the_board_is_readable_on_the_big_screen_and_the_phone_page_does_not_scroll_sideways(
    open_page, operator, screenshots
):
    board = open_page("/board", *BIG_SCREEN)
    phone = open_page(REPORT_PAGE, *PHONE, phone=True)
    send_voice_note(phone, scene.COUNTER_FILE)
    expect(phone.locator("#chat li.theirs")).to_have_count(1, timeout=8000)
    case = board.locator("article[data-case]")
    expect(case).to_have_count(1, timeout=8000)

    board.screenshot(path=screenshots / "board_1920x1080.png")
    phone.screenshot(path=screenshots / "phone_390x844.png", full_page=True)

    assert board.evaluate(SIDEWAYS_SCROLL) <= 0, "the board scrolls sideways at 1920 wide"
    texts = board.evaluate(MEASURE_TEXT)
    small = [t for t in texts if t["size"] < 16]
    assert not small, f"text smaller than 16px on the board: {small}"
    cut = [t for t in texts if t["cut"]]
    assert not cut, f"text cut off on the board: {cut}"
    assert float(case.locator(".case-type").evaluate("el => getComputedStyle(el).fontSize").removesuffix("px")) >= 28
    box = case.bounding_box()
    assert box["x"] >= 0 and box["x"] + box["width"] <= BIG_SCREEN[0], "the case card goes past the edge of the screen"

    assert phone.evaluate(SIDEWAYS_SCROLL) <= 0, "the phone page scrolls sideways at 390 wide"
