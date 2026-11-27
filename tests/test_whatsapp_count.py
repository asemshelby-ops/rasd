"""The local WhatsApp counting tool. Every export here is FAKE and written in this file.

The tool reads a WhatsApp text export on the owner's own laptop and prints
aggregates only. No network, no AI model.
"""

import ast
import csv
import os
import subprocess
import sys
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from whatsapp_count.__main__ import inside_repository, main
from whatsapp_count.counting import count, render
from whatsapp_count.export import parse_export, read_export
from whatsapp_count.handcheck import score, write_sample
from whatsapp_count.rules import looks_like_closure, looks_like_report, names_hotel, names_room

REPO = Path(__file__).resolve().parent.parent
START = datetime(2026, 12, 23, 9, 0)

ARABIC_DIGITS = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")
RLM = "‏"

# A fake group. (minutes after START, sender, text). Names, numbers and messages are invented.
GROUP = [
    (0, "أبو فهد", "صباح الخير، الحضور كامل"),
    (2, "ماجد العتيبي", "حاضر"),
    (5, "استقبال ١", "حاج ضيّع بطاقة نسك في فندق الواحة غرفة 412"),
    (9, "صيانة", "المكيف خربان في غرفة 318"),
    (12, "ماجد العتيبي", "أحد عنده شاحن؟"),
    (27, "أبو فهد", "لقيناها 👍"),
    (40, "استقبال ١", "في حاجة كبيرة تايهة عند البوابة، جوال ابنها 0551234567"),
    (55, "صيانة", "الموية مقطوعة عن الدور الثالث في برج النور"),
    (70, "صيانة", "تم"),
    (300, "استقبال ١", "الشنط ما وصلت للحجاج"),
]


def android_english(group=GROUP, start=START) -> str:
    lines = ["12/23/26, 8:55 AM - Messages and calls are end-to-end encrypted."]
    for minutes, sender, text in group:
        at = start + timedelta(minutes=minutes)
        hour = at.strftime("%I").lstrip("0")
        lines.append(f"{at.month}/{at.day}/{at:%y}, {hour}:{at:%M} {at:%p} - {sender}: {text}")
    return "\n".join(lines) + "\n"


def android_arabic(group=GROUP, start=START) -> str:
    lines = []
    for minutes, sender, text in group:
        at = start + timedelta(minutes=minutes)
        half = "ص" if at.hour < 12 else "م"
        hour = at.strftime("%I").lstrip("0")
        stamp = f"{at.day}{RLM}/{at.month}{RLM}/{at.year}، {hour}:{at:%M} {half}".translate(ARABIC_DIGITS)
        lines.append(f"{stamp} - {sender}: {text}")
    return "\n".join(lines) + "\n"


def iphone(group=GROUP, start=START) -> str:
    lines = []
    for minutes, sender, text in group:
        at = start + timedelta(minutes=minutes)
        lines.append(f"‎[{at:%d/%m/%Y}, {at:%H:%M:%S}] {sender}: {text}")
    return "\n".join(lines) + "\n"


def messages(text, **options):
    return parse_export(text, **options).messages


# --- 1. reading the export ------------------------------------------------------------------------


@pytest.mark.parametrize("export", [android_english, android_arabic, iphone])
def test_every_export_style_gives_the_same_messages(export):
    read = messages(export())
    assert len(read) == len(GROUP)
    assert [m.at for m in read] == [START + timedelta(minutes=minutes) for minutes, _, _ in GROUP]
    assert [m.text for m in read] == [text for _, _, text in GROUP]


def test_arabic_digits_and_morning_evening_marks_are_read():
    evening = android_arabic([(0, "س", "السلام عليكم")], start=datetime(2026, 12, 23, 21, 41))
    assert messages(evening)[0].at == datetime(2026, 12, 23, 21, 41)


def test_twelve_at_night_and_twelve_at_noon():
    text = "12/23/26, 12:05 AM - A: one\n12/23/26, 12:05 PM - A: two\n"
    assert [m.at.hour for m in messages(text)] == [0, 12]


def test_a_message_of_several_lines_stays_one_message():
    text = "23/12/2026, 09:05 - استقبال: حاج ضيّع بطاقته\nفندق الواحة\nغرفة 412\n23/12/2026, 09:06 - ماجد: تمام\n"
    read = messages(text)
    assert len(read) == 2 and read[0].text == "حاج ضيّع بطاقته\nفندق الواحة\nغرفة 412"


def test_system_lines_are_not_messages():
    text = "23/12/2026, 09:00 - أبو فهد added ماجد\n23/12/2026, 09:05 - ماجد: حاضر\n"
    assert len(messages(text)) == 1


@pytest.mark.parametrize("placeholder", ["<Media omitted>", "<تم استبعاد الوسائط>", "‎image omitted", "‎صورة محذوفة", "<attached: 00000012-PHOTO.jpg>"])
def test_a_photo_is_counted_as_a_message_and_never_read(placeholder):
    (message,) = messages(f"23/12/2026, 09:05 - ماجد: {placeholder}\n")
    assert message.media is True and message.text == ""


def test_day_first_and_month_first_are_told_apart_by_the_dates_themselves():
    assert messages("23/12/2026, 09:05 - A: x\n")[0].at.month == 12  # 23 cannot be a month
    assert messages("12/23/2026, 09:05 - A: x\n")[0].at.month == 12  # 23 cannot be a month here either
    assert messages("2026-12-23, 09:05 - A: x\n")[0].at == datetime(2026, 12, 23, 9, 5)


def test_a_date_that_could_be_either_is_read_day_first_and_the_tool_says_so():
    parsed = parse_export("05/06/2026, 09:05 - A: x\n")
    assert parsed.messages[0].at == datetime(2026, 6, 5, 9, 5)
    assert "date_order_assumed" in parsed.notes
    assert parse_export("05/06/2026, 09:05 - A: x\n", month_first=True).messages[0].at == datetime(2026, 5, 6, 9, 5)


def test_dates_in_the_hijri_calendar_keep_their_distances():
    text = "04/07/1448, 09:05 - A: one\n04/07/1448, 09:35 - A: two\n06/07/1448, 09:35 - A: three\n"
    parsed = parse_export(text)
    first, second, third = (m.at for m in parsed.messages)
    assert second - first == timedelta(minutes=30) and third - second == timedelta(days=2)
    assert "hijri_dates" in parsed.notes


def test_a_file_that_is_not_an_export_gives_no_messages():
    assert messages("just some text\nand more\n") == []


def test_an_export_inside_a_zip_file_is_read(tmp_path):
    with zipfile.ZipFile(tmp_path / "chat.zip", "w") as archive:
        archive.writestr("_chat.txt", iphone())
    assert len(messages(read_export(tmp_path / "chat.zip"))) == len(GROUP)


# --- 2. which messages look like reports --------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "حاج ضيّع بطاقة نسك في فندق الواحة غرفة 412",
        "المكيف خربان في غرفة 318",
        "في حاجة كبيرة تايهة عند البوابة",
        "الموية مقطوعة عن الدور الثالث",
        "الشنط ما وصلت للحجاج",
        "الحاج مريض ويحتاج دواه",
        "المصعد عطلان",
        "ایک حاجی گم ہو گیا ہے",
        "AC not working in room 204",
    ],
)
def test_a_message_about_a_problem_looks_like_a_report(text):
    assert looks_like_report(text)


@pytest.mark.parametrize("text", ["صباح الخير، الحضور كامل", "حاضر", "أحد عنده شاحن؟", "لقيناها 👍", "تم", "جزاكم الله خير", "غرفة 412 جاهزة", ""])
def test_chat_attendance_and_replies_do_not_look_like_reports(text):
    assert not looks_like_report(text)


@pytest.mark.parametrize("text", ["الوجبات ما وصلت", "وين الشنط؟", "الحاج يحتاج دواء", "مافي موية في الدور كله", "پانی نہیں ہے"])
def test_a_thing_that_is_missing_or_needed_looks_like_a_report(text):
    assert looks_like_report(text)


@pytest.mark.parametrize("text", ["تم توزيع الوجبات", "عاجل: الباص يتحرك 9", "الدوام يبدأ 8", "المكيف شغال الحمدلله", "وصلت الشنط كلها"])
def test_a_topic_word_alone_is_not_a_report(text):
    assert not looks_like_report(text)


def test_a_name_that_only_contains_a_keyword_is_not_a_report():
    assert not looks_like_report("أسماء وهديل وصلوا")  # "ماء" and "هدي" are inside names


# --- 3. hotel, room, closure -----------------------------------------------------------------------------


def test_a_hotel_is_named_by_its_word_or_by_the_teams_own_list():
    assert names_hotel("ضاعت بطاقته في فندق الواحة")
    assert names_hotel("الموية مقطوعة في برج النور")
    assert names_hotel("ببرج النور في مشكلة")
    assert not names_hotel("ضاعت بطاقته عند البوابة")
    assert names_hotel("المكيف خربان في الواحة", hotels=["الواحة"])


def test_a_room_is_named_with_its_number_in_either_digit_style():
    assert names_room("المكيف خربان في غرفة 318")
    assert names_room("المكيف خربان في غرفة ٣١٨")
    assert names_room("المكيف خربان بالغرفة رقم 318")
    assert names_room("AC not working in room 204")
    assert names_room("غرفة تسعمية وسبعة ما فيها موية")
    assert not names_room("المكيف خربان في الغرفة")
    assert not names_room("جواله 0551234567")


@pytest.mark.parametrize("text", ["لقيناها 👍", "لقيناه", "تم", "تم الحل", "خلاص انحلت", "👍", "✅", "done", "found it", "تمت المعالجة"])
def test_closure_like_replies(text):
    assert looks_like_closure(text)


@pytest.mark.parametrize("text", ["حاضر", "أحد عنده شاحن؟", "المكيف خربان في غرفة 318", "لقينا حاج تايه عند البوابة ما يعرف فندقه", "تمام بس المكيف لسا خربان"])
def test_not_every_reply_is_a_closure(text):
    assert not looks_like_closure(text)


# --- 4. the counts -----------------------------------------------------------------------------------------


def counts_of(group=GROUP, **options):
    return count(messages(android_english(group)), **options)


def test_the_counts_of_the_fake_group():
    counts = counts_of()
    assert counts.messages == 10
    assert counts.reports == 5  # lost card, AC, lost pilgrim, water, luggage
    assert counts.missing_hotel == 3  # AC, lost pilgrim, luggage
    assert counts.missing_room == 3  # lost pilgrim, water (a floor is not a room), luggage
    assert counts.missing_either == 4  # only the lost card names both
    assert counts.no_closure == 3
    assert counts.closure_minutes == [18.0, 15.0]  # AC -> "لقيناها" (27-9), water -> "تم" (70-55)
    assert counts.median_minutes == 16.5


def test_a_closure_reply_closes_only_the_latest_open_report():
    group = [(0, "أ", "المكيف خربان في غرفة 318"), (5, "ب", "المصعد عطلان في برج النور"), (9, "ج", "تم")]
    counts = counts_of(group)
    assert counts.reports == 2 and counts.no_closure == 1 and counts.closure_minutes == [4.0]


def test_a_reply_before_the_report_or_long_after_it_does_not_close_it():
    group = [(0, "أ", "تم"), (5, "ب", "المصعد عطلان في برج النور"), (5 + 25 * 60, "ج", "تم")]
    assert counts_of(group).no_closure == 1
    assert counts_of(group, window_hours=48).no_closure == 0


def test_no_reports_means_no_shares_and_no_median():
    counts = counts_of([(0, "أ", "حاضر")])
    assert counts.reports == 0 and counts.median_minutes is None
    assert "0" in render(counts, notes=())


def test_the_printed_report_has_only_aggregates():
    parsed = parse_export(android_english())
    text = render(count(parsed.messages), parsed.notes)
    for _, sender, _ in GROUP:
        assert sender not in text
    for private in ("الواحة", "النور", "البوابة", "شاحن", "صباح", "ضيّع", "خربان", "تايهة", "الشنط", "ماجد", "فهد"):
        assert private not in text, private
    assert "0551234567" not in text and "412" not in text and "318" not in text
    assert "عدد الرسائل" in text and "10" in text
    assert "60%" in text  # 3 of 5 reports have no visible closure
    assert "16.5" in text or "17" in text


# --- 5. the hand check -----------------------------------------------------------------------------------------


def test_the_hand_check_file_has_fifty_random_messages_and_no_names_or_long_numbers(tmp_path):
    group = [(i, f"موظف {i}", f"رسالة رقم {i} والجوال 0551234567") for i in range(120)]
    read = messages(android_english(group))
    path = tmp_path / "check.csv"
    assert write_sample(read, path, size=50, seed=7) == 50
    rows = list(csv.DictReader(path.open(encoding="utf-8-sig")))
    assert len(rows) == 50 and len({row["id"] for row in rows}) == 50
    everything = path.read_text(encoding="utf-8-sig")
    assert "موظف" not in everything and "0551234567" not in everything
    assert all(row["report"] == "" for row in rows)  # the owner fills this in; the tool's own answer is not shown


def test_fewer_than_fifty_messages_are_all_written(tmp_path):
    assert write_sample(messages(android_english()), tmp_path / "check.csv", size=50, seed=1) == len(GROUP)


def test_the_agreement_rate_compares_the_owners_marks_with_the_rules(tmp_path):
    read = messages(android_english())
    path = tmp_path / "check.csv"
    write_sample(read, path, size=50, seed=1)
    rows = list(csv.DictReader(path.open(encoding="utf-8-sig")))
    for row in rows:
        row["report"] = "y" if looks_like_report(read[int(row["id"])].text) else "n"
    wrong = next(row for row in rows if row["report"] == "n")
    wrong["report"] = "نعم"  # the owner says this one IS a report; the rules said no
    rows[-1]["report"] = "" if rows[-1] is not wrong else rows[-1]["report"]
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    result = score(read, path)
    assert result.unmarked == (0 if rows[-1] is wrong else 1)
    assert result.marked == len(rows) - result.unmarked
    assert result.agree == result.marked - 1
    assert result.owner_yes_tool_no == 1 and result.owner_no_tool_yes == 0


def test_a_hand_check_file_from_another_export_is_refused(tmp_path):
    path = tmp_path / "check.csv"
    write_sample(messages(android_english()), path, size=50, seed=1)
    other = messages(android_english([(i, "أ", f"كلام آخر {i}") for i in range(10)]))
    with pytest.raises(ValueError):
        score(other, path)


# --- the command, and where it refuses to work --------------------------------------------------------------------


def test_the_command_prints_the_counts_and_saves_them_next_to_the_export(tmp_path, capsys):
    export = tmp_path / "group.txt"
    export.write_text(android_arabic(), encoding="utf-8")
    assert main([str(export)]) == 0
    printed = capsys.readouterr().out
    assert "عدد الرسائل" in printed
    assert (tmp_path / "group.rasd_counts.txt").read_text(encoding="utf-8").strip() in printed


def test_the_command_refuses_an_export_inside_the_repository(tmp_path, capsys):
    inside = REPO / "data" / "not_really_an_export.txt"
    assert inside_repository(inside) and not inside_repository(tmp_path / "group.txt")
    assert main([str(inside)]) != 0
    assert "inside the repository" in capsys.readouterr().err


def test_the_command_says_so_when_the_file_is_missing_or_not_an_export(tmp_path, capsys):
    assert main([str(tmp_path / "nothing.txt")]) != 0
    (tmp_path / "notes.txt").write_text("hello\n", encoding="utf-8")
    assert main([str(tmp_path / "notes.txt")]) != 0
    assert "no WhatsApp messages" in capsys.readouterr().err


def test_the_hand_check_command_writes_the_file_and_then_scores_it(tmp_path, capsys):
    export = tmp_path / "group.txt"
    export.write_text(iphone(), encoding="utf-8")
    assert main([str(export), "--hand-check"]) == 0
    check = tmp_path / "group.rasd_hand_check.csv"
    rows = list(csv.DictReader(check.open(encoding="utf-8-sig")))
    read = messages(iphone())
    for row in rows:
        row["report"] = "1" if looks_like_report(read[int(row["id"])].text) else "0"
    with check.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    capsys.readouterr()
    assert main([str(export), "--score", str(check)]) == 0
    assert "100%" in capsys.readouterr().out


def test_scoring_on_a_terminal_that_cannot_show_arabic_saves_the_result_and_says_where(tmp_path):
    export = tmp_path / "group.txt"
    export.write_text(iphone(), encoding="utf-8")
    assert main([str(export), "--hand-check"]) == 0
    command = [sys.executable, "-m", "whatsapp_count", str(export), "--score", str(tmp_path / "group.rasd_hand_check.csv")]
    plain_terminal = {**os.environ, "PYTHONIOENCODING": "cp1252", "PYTHONUTF8": "0"}
    result = subprocess.run(command, cwd=REPO, env=plain_terminal, capture_output=True, text=True, encoding="cp1252", errors="replace")
    assert result.returncode == 0, result.stderr
    saved = tmp_path / "group.rasd_agreement.txt"
    assert str(saved) in result.stdout
    assert "report" in saved.read_text(encoding="utf-8")  # nothing marked yet: the saved text says to fill the report column


def test_exports_and_what_is_made_from_them_are_ignored_by_git():
    names = [
        "WhatsApp Chat with Group.txt", "WhatsApp Chat - Group.zip", "_chat.txt", "x/group.rasd_counts.txt", "group.rasd_hand_check.csv",
        "group.rasd_agreement.txt",
    ]  # fmt: skip
    for name in names:
        result = subprocess.run(["git", "check-ignore", "-q", name], cwd=REPO)
        assert result.returncode == 0, f"{name} is not ignored"


# --- strictly local: no network library, no AI model -------------------------------------------------------------------

NETWORK_MODULES = {
    "socket", "ssl", "http", "http.client", "http.server", "urllib.request", "urllib3", "requests", "httpx", "httpx2",
    "aiohttp", "websockets", "ftplib", "smtplib", "poplib", "imaplib", "telnetlib", "xmlrpc", "asyncio", "socketserver",
    "anthropic", "openai", "webbrowser", "rasd", "app",
}  # fmt: skip


def test_running_the_tool_loads_no_network_library_and_no_ai_model(tmp_path):
    export = tmp_path / "group.txt"
    export.write_text(android_arabic(), encoding="utf-8")
    program = (
        "import sys\n"
        "from whatsapp_count.__main__ import main\n"
        f"main([{str(export)!r}])\n"
        f"main([{str(export)!r}, '--hand-check'])\n"
        f"main([{str(export)!r}, '--score', {str(tmp_path / 'group.rasd_hand_check.csv')!r}])\n"
        f"banned = {sorted(NETWORK_MODULES)!r}\n"
        "loaded = sorted(name for name in banned if name in sys.modules)\n"
        "print('LOADED:' + ','.join(loaded))\n"
    )
    result = subprocess.run([sys.executable, "-c", program], cwd=REPO, capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().splitlines()[-1] == "LOADED:"


def test_no_file_of_the_tool_imports_a_network_library_anywhere():
    """Also catches an import hidden inside a function, which the test above would not load."""
    for file in sorted((REPO / "whatsapp_count").glob("*.py")):
        for node in ast.walk(ast.parse(file.read_text(encoding="utf-8"))):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            for name in names:
                parts = name.split(".")
                prefixes = {".".join(parts[: i + 1]) for i in range(len(parts))}
                assert not prefixes & NETWORK_MODULES, f"{file.name} imports {name}"
            if isinstance(node, ast.Call) and getattr(node.func, "id", "") in ("__import__", "exec", "eval"):
                raise AssertionError(f"{file.name} calls {node.func.id}")


# --- what the code review found (stage 6) --------------------------------------------------------------------


def test_a_line_whose_date_cannot_be_read_is_not_glued_to_the_message_before_it():
    text = "05/06/2026, 09:05 - أحمد: المكيف خربان\n25/06/2026, 09:06 - سالم العتيبي: تم\n"
    parsed = parse_export(text, month_first=True)  # the wrong order on purpose: 25 is not a month
    assert [m.text for m in parsed.messages] == ["المكيف خربان"]
    assert "سالم العتيبي" not in parsed.messages[0].text
    assert parsed.unread_lines == 1


def test_the_command_stops_when_most_dates_cannot_be_read(tmp_path, capsys):
    export = tmp_path / "group.txt"
    export.write_text(iphone(), encoding="utf-8")  # day first; 23 is not a month
    assert main([str(export), "--month-first"]) != 0
    assert "dates" in capsys.readouterr().err


@pytest.mark.parametrize("header", ["04/07/1448 هـ, 09:05 - A: one", "04/07/1448 AH, 09:05 - A: one", "[04/07/1448 هـ, 09:05:00] A: one"])
def test_a_hijri_date_with_its_era_mark_is_read(header):
    assert len(messages(header + "\n")) == 1


def test_a_hotel_word_must_be_a_word_and_be_followed_by_a_name():
    assert not names_hotel("برجع لكم بعد شوي")
    assert not names_hotel("المكيف خربان في الفندق")
    assert names_hotel("المكيف خربان في فندق الواحة")


def test_a_bare_room_number_counts_as_a_room():
    assert names_room("مكيف 318 خربان")
    assert not names_room("الباص يتحرك 9:30")
    assert not names_room("وصل 45 حاج")


def test_praise_with_the_word_ma_is_not_a_report():
    assert not looks_like_report("ما شاء الله الوجبات ممتازة")
    assert looks_like_report("الوجبات ما وصلت")


def hand_check_rows(tmp_path, texts):
    read = messages(android_english([(i, "أ", text) for i, text in enumerate(texts)]))
    path = tmp_path / "check.csv"
    write_sample(read, path, size=50, seed=1)
    return read, path, list(csv.DictReader(path.open(encoding="utf-8-sig")))


def test_a_message_that_starts_like_a_spreadsheet_formula_is_written_as_plain_text(tmp_path):
    _, _, rows = hand_check_rows(tmp_path, ['=HYPERLINK("http://example.invalid","x")', "+966 55 123 4567 جواله", "-1 مكيف", "@all الحضور"])
    assert len(rows) == 4
    assert not any(row["text"].lstrip()[:1] in ("=", "+", "-", "@") for row in rows)
    assert rows[0]["text"].startswith("'=")


def test_phone_numbers_written_in_groups_and_passport_numbers_are_masked(tmp_path):
    _, path, _ = hand_check_rows(tmp_path, ["جواله +966 55 123 4567", "رقمه 055 123 4567", "جوازه AB123456", "غرفة 412"])
    everything = path.read_text(encoding="utf-8-sig")
    assert "4567" not in everything and "AB123456" not in everything
    assert "412" in everything  # a room number stays: the owner needs it to judge


def test_the_check_value_can_never_be_mistaken_for_a_number_by_a_spreadsheet(tmp_path):
    _, _, rows = hand_check_rows(tmp_path, [f"رسالة {i}" for i in range(40)])
    assert all(row["check"].startswith("h") for row in rows)


def test_a_marked_file_saved_with_semicolons_is_still_read(tmp_path):
    read, path, rows = hand_check_rows(tmp_path, ["المكيف خربان", "حاضر"])
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]), delimiter=";")
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "report": "y" if looks_like_report(read[int(row["id"])].text) else "n"})
    assert score(read, path).agree == 2


def test_a_marked_file_in_an_old_windows_arabic_encoding_is_still_read(tmp_path):
    read, path, rows = hand_check_rows(tmp_path, ["المكيف خربان", "حاضر"])
    with path.open("w", encoding="cp1256", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "report": "نعم" if looks_like_report(read[int(row["id"])].text) else "لا"})
    assert score(read, path).agree == 2
