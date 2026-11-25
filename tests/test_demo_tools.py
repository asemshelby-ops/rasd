"""The demo-day tools: the voice-to-board timer, and the helper that starts the site for phones.

No AI model and no network here.
"""

import ipaddress

from cryptography import x509

from demo.certificate import certificate_covers, make_certificate
from demo.measure_time import TARGET_SECONDS, measure_once, render
from demo.run import address_lines
from rasd.voice import FirstThatWorks, VoiceError


class FakeClock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        assert seconds >= 0
        self.now += seconds


# --- the timer ---------------------------------------------------------------------------------------


def run_once(read_seconds, phase, merged=True, board_fetch=0.05):
    clock = FakeClock()

    def send():
        clock.now += read_seconds
        return {"merged": merged, "seconds": {"heard": 0.0, "read": read_seconds, "total": read_seconds}}

    def board():
        clock.now += board_fetch
        return [{"count": 2 if merged else 1}]

    return measure_once(send, board, phase=phase, clock=clock, sleep=clock.sleep, interval=1.0, limit=5.0)


def test_the_case_is_seen_at_the_boards_next_question_after_it_was_stored():
    # the board asks at 0.3, 1.3, 2.3, 3.3 ... seconds; the case is stored at 2.4
    result = run_once(read_seconds=2.4, phase=0.3)
    assert result["reply"] == 2.4
    assert result["board"] == 3.35
    assert result["merged"] is True


def test_a_board_question_that_falls_right_after_storing_shows_the_case_at_once():
    assert run_once(read_seconds=2.4, phase=0.45)["board"] == 2.5


def test_a_note_that_never_merges_is_reported_as_not_merged_and_not_as_a_time():
    result = run_once(read_seconds=2.0, phase=0.3, merged=False)
    assert result["merged"] is False and result["board"] is None


def test_the_report_says_the_target_each_run_and_whether_it_was_met():
    runs = [
        {"reply": 2.4, "board": 3.35, "merged": True, "seconds": {"heard": 0.0, "read": 2.4, "total": 2.4}},
        {"reply": 3.1, "board": 3.6, "merged": True, "seconds": {"heard": 0.0, "read": 3.1, "total": 3.1}},
    ]
    text = render(runs, speech_live=False, replay=False, cost=0.0021)
    assert TARGET_SECONDS == 8
    assert "الهدف: أقل من 8 ثوانٍ" in text
    assert "3.35" in text and "3.60" in text
    assert "ضمن الهدف" in text and "تجاوز الهدف" not in text
    assert "$0.0021" in text


def test_the_report_says_so_when_speech_to_text_was_not_part_of_the_measurement():
    runs = [{"reply": 2.4, "board": 3.35, "merged": True, "seconds": {"heard": 0.0, "read": 2.4, "total": 2.4}}]
    assert "لم يدخل في القياس" in render(runs, speech_live=False, replay=False, cost=0.0)
    assert "لم يدخل في القياس" not in render(runs, speech_live=True, replay=False, cost=0.0)


def test_a_run_over_the_target_or_not_merged_fails_the_report():
    slow = [{"reply": 8.2, "board": 8.9, "merged": True, "seconds": {"heard": 3.0, "read": 5.2, "total": 8.2}}]
    assert "تجاوز الهدف" in render(slow, speech_live=True, replay=False, cost=0.0)
    lost = [{"reply": 2.0, "board": None, "merged": False, "seconds": {"heard": 0.0, "read": 2.0, "total": 2.0}}]
    text = render(lost, speech_live=True, replay=False, cost=0.0)
    assert "لم تُدمج" in text and "ضمن الهدف" not in text


# --- a live transcriber that hears nothing falls back to the saved words ---------------------------------


class Hears:
    def __init__(self, text=None):
        self.text = text

    def transcribe(self, audio, filename):
        if self.text is None:
            raise VoiceError("down")
        return self.text


def test_when_the_live_transcriber_hears_nothing_the_saved_words_are_used():
    assert FirstThatWorks(Hears("  "), Hears("النص المحفوظ")).transcribe(b"a", "a.wav") == "النص المحفوظ"


def test_the_live_transcriber_is_used_when_it_hears_something():
    assert FirstThatWorks(Hears("سمعت"), Hears("النص المحفوظ")).transcribe(b"a", "a.wav") == "سمعت"


def test_when_nobody_hears_anything_the_answer_is_empty_not_an_error():
    assert FirstThatWorks(Hears(""), Hears("")).transcribe(b"a", "a.wav") == ""


# --- starting the site for phones on the hotspot -----------------------------------------------------------


def test_the_certificate_names_the_laptop_addresses_so_phones_can_record(tmp_path):
    make_certificate(tmp_path, ["192.168.43.120"])
    certificate = x509.load_pem_x509_certificate((tmp_path / "cert.pem").read_bytes())
    names = certificate.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert ipaddress.ip_address("192.168.43.120") in names.get_values_for_type(x509.IPAddress)
    assert ipaddress.ip_address("127.0.0.1") in names.get_values_for_type(x509.IPAddress)
    assert "localhost" in names.get_values_for_type(x509.DNSName)
    assert (tmp_path / "key.pem").read_bytes().startswith(b"-----BEGIN")


def test_a_certificate_is_made_again_only_when_the_address_changed(tmp_path):
    assert certificate_covers(tmp_path, ["192.168.43.120"]) is False  # none yet
    make_certificate(tmp_path, ["192.168.43.120"])
    assert certificate_covers(tmp_path, ["192.168.43.120"]) is True
    assert certificate_covers(tmp_path, ["172.20.10.2"]) is False  # another hotspot gave another address


def test_the_helper_prints_the_addresses_to_open_on_the_laptop_and_on_the_phones():
    lines = address_lines(["192.168.43.120"], port=8443, https=True)
    text = "\n".join(lines)
    assert "https://localhost:8443/board" in text
    assert "https://192.168.43.120:8443/report" in text
    assert "https://192.168.43.120:8443/operator" in text


def test_without_https_the_helper_warns_that_phones_cannot_record():
    text = "\n".join(address_lines(["192.168.43.120"], port=8000, https=False))
    assert "http://192.168.43.120:8000/report" in text
    assert "cannot record" in text
