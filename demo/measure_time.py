"""Measures the time from the end of a voice note to the merged case on the board.

    python -m demo.measure_time             three runs with the real model
    python -m demo.measure_time --runs 5
    python -m demo.measure_time --replay    the replay path (saved files, no network, no cost)

Each run plays the scene on a real local server: the counter employee's note is
sent first; then the clock starts, the pilgrim's note is sent, and the clock
stops when the board (which asks the server once a second) shows one case with
two reports. The report is printed in Arabic and saved in measurements/.

What it cannot measure today: live speech to text. Without RASD_OPENAI_KEY the
words come from the saved transcript, and the report says so.
"""

import argparse
import os
import random
import sys
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path

TARGET_SECONDS = 8
REPORT_FILE = Path(__file__).resolve().parent.parent / "measurements" / "stage4_voice_to_board.txt"


def measure_once(send, board, phase: float, clock=time.perf_counter, sleep=time.sleep, interval: float = 1.0, limit: float = 30.0) -> dict:
    """One measurement. send() sends the second voice note; board() returns the board's cases.

    The board asks the server every `interval` seconds; `phase` says where in that
    cycle the voice note ended. The clock stops when a board question shows the
    merged case.
    """
    started = clock()
    reply = send()
    replied = clock() - started
    result = {"reply": round(replied, 2), "board": None, "merged": False, "seconds": reply.get("seconds")}
    tick = phase
    while tick < replied:  # the first board question after the case was stored
        tick += interval
    while tick <= limit:
        wait = started + tick - clock()
        if wait > 0:
            sleep(wait)
        if any(case["count"] >= 2 for case in board()):
            result["board"] = round(clock() - started, 2)
            result["merged"] = True
            return result
        if not reply.get("merged"):
            return result  # the note did not merge: no later question will show it
        tick += interval
    return result


def render(runs: list[dict], speech_live: bool, replay: bool, cost: float, refresh: float = 1.0) -> str:
    """The report, in Arabic."""
    lines = [
        "قياس الزمن من نهاية الرسالة الصوتية إلى ظهور الحالة المدموجة على اللوحة",
        f"التاريخ: {datetime.now():%Y-%m-%d %H:%M}",
        f"الهدف: أقل من {TARGET_SECONDS} ثوانٍ",
        "المسار: " + ("إعادة من ملفات محفوظة، دون شبكة" if replay else "مباشر، بالنموذج الحقيقي"),
    ]
    if speech_live:
        lines.append("تحويل الصوت إلى نص: مباشر، وداخل في القياس.")
    else:
        lines.append("تحويل الصوت إلى نص: لم يدخل في القياس. لا مفتاح للخدمة، فأُخذ النص من ملف محفوظ.")
    lines.append("")
    for number, run in enumerate(runs, start=1):
        took = run["seconds"] or {}
        parts = f"تحويل الصوت {took.get('heard', 0):.2f} ث، القراءة والتسجيل {took.get('read', 0):.2f} ث، الرد على المرسل {run['reply']:.2f} ث"
        if run["merged"]:
            lines.append(f"التشغيل {number}: {parts}، الظهور على اللوحة {run['board']:.2f} ث")
        else:
            lines.append(f"التشغيل {number}: {parts}. لم تُدمج الرسالة الثانية في الحالة.")
    lines.append("")
    merged = [run["board"] for run in runs if run["merged"]]
    if len(merged) < len(runs):
        lines.append(f"النتيجة: لم تُدمج الرسالة الثانية في {len(runs) - len(merged)} من {len(runs)}. القياس غير مكتمل.")
    elif max(merged) < TARGET_SECONDS:
        lines.append(f"النتيجة: ضمن الهدف. الأقصر {min(merged):.2f} ث، والأطول {max(merged):.2f} ث، في {len(runs)} تشغيلات.")
    else:
        lines.append(f"النتيجة: تجاوز الهدف. الأطول {max(merged):.2f} ث.")
    lines.append(f"اللوحة تسأل الخادم كل {refresh:g} ثانية، فالظهور يتأخر عن التسجيل ثانية واحدة على الأكثر.")
    lines.append("القياس على الحاسوب نفسه. على شبكة الجوال يُضاف زمن رفع الرسالة من الجوال.")
    lines.append(f"التكلفة التقريبية لهذا القياس: ${cost:.4f}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure the time from a voice note to the merged case on the board.")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--replay", action="store_true", help="measure the replay path (saved files, no network)")
    options = parser.parse_args()

    import httpx
    import uvicorn

    from app.engine import LiveEngine, ReplayEngine
    from app.main import BOARD_REFRESH_SECONDS, create_app
    from demo import scene
    from rasd.cost import cost_usd
    from rasd.understand import DEFAULT_MODEL
    from rasd.voice import OPENAI_KEY_VARIABLE

    spent = {"input": 0, "output": 0}
    if options.replay:
        engine = ReplayEngine()
    else:
        engine = LiveEngine()
        live_read = engine.read

        def counted(text, photo_attached=False):
            report = live_read(text, photo_attached=photo_attached)
            spent["input"] += report.input_tokens
            spent["output"] += report.output_tokens
            return report

        engine.read = counted

    with tempfile.TemporaryDirectory() as folder:
        app = create_app(engine=engine, db_path=Path(folder) / "measure.db")
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning"))
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        while not server.started:
            time.sleep(0.05)
        port = server.servers[0].sockets[0].getsockname()[1]
        runs = []
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=60.0) as site:

            def voice(file_name):
                audio = (scene.SCENE_DIR / file_name).read_bytes()
                reply = site.post("/api/voice", data={"hotel": scene.REPORTING_HOTEL}, files={"audio": (file_name, audio)})
                if reply.status_code != 200:
                    sys.exit(f"The voice note was not accepted ({reply.status_code}): {reply.json().get('message')}")
                return reply.json()

            for _ in range(options.runs):
                site.post("/api/operator/reset", data={"confirm": "yes"})
                voice(scene.COUNTER_FILE)
                runs.append(
                    measure_once(
                        lambda: voice(scene.PILGRIM_FILE),
                        lambda: site.get("/api/board").json()["cases"],
                        phase=random.random() * BOARD_REFRESH_SECONDS,
                        interval=BOARD_REFRESH_SECONDS,
                    )
                )
        server.should_exit = True
        thread.join(timeout=5)

    speech_live = bool(os.environ.get(OPENAI_KEY_VARIABLE, "").strip()) and not options.replay
    text = render(runs, speech_live, options.replay, cost_usd(DEFAULT_MODEL, spent["input"], spent["output"]), BOARD_REFRESH_SECONDS)
    print(text)
    if not options.replay:
        REPORT_FILE.parent.mkdir(exist_ok=True)
        REPORT_FILE.write_text(text + "\n", encoding="utf-8")
        print(f"\nSaved to {REPORT_FILE}")


if __name__ == "__main__":
    main()
