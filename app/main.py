"""The pages of the demo: the reporting page, the board, the Elm view and the before-and-after page.

    uvicorn app.main:app --host 0.0.0.0 --port 8000

FastAPI, one SQLite file, plain HTML pages, no build step. The rules live in
rasd/; this file only receives requests, calls the rules and shows the result.

What the big screen may show is decided in app/store.py (Store.board): no full
name, no passport or visa number, no words of a message, no photo.
"""

import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import copy
from app.intake import listed_hotel, take_in
from app.store import SAVED_SOURCE, CaseClosed, NoSuchCase, NothingToAnswer, Store
from demo import scene
from rasd.askback import ask_back
from rasd.elm import SimulatedElm
from rasd.privacy import redact
from rasd.text import to_western_digits
from rasd.routing import CHECKLISTS, HOTELS
from rasd.understand import KEY_VARIABLE
from rasd.voice import OPENAI_KEY_VARIABLE, VoiceError

log = logging.getLogger("rasd")
HERE = Path(__file__).resolve().parent
PROJECT_DIR = HERE.parent
DEFAULT_DB = PROJECT_DIR / "rasd.db"
BEFORE_AFTER_FILE = PROJECT_DIR / "demo" / "before_after.json"

# How often the board asks the server for news. The time from a voice note to
# the case on the big screen is the reading time plus, at most, this.
BOARD_REFRESH_SECONDS = 1

# Uploads larger than these are refused with a message that says what to do.
# The reporting page makes photos smaller before sending, so a normal photo fits.
MAX_PHOTO_BYTES = 4_000_000
MAX_AUDIO_BYTES = 15_000_000

# The operator's switch (the /operator page): "live" reads with the model,
# "replay" answers the demo scene from saved files with no network.
MODES = ("live", "replay")

# The operator page and the supervisor page ask for a PIN. It is read from RASD_PIN
# (in the .env file). When that is not set, a random one is made at start and printed in
# the terminal. "off" turns the PIN off; the tests use that, and nobody else should.
PIN_VARIABLE = "RASD_PIN"
PIN_OFF = "off"
PIN_PROTECTED = ("/operator", "/api/operator", "/supervisor")
PIN_TRIES = 5
PIN_LOCK_SECONDS = 60


def pin_for_this_run() -> str:
    load_dotenv(PROJECT_DIR / ".env")
    pin = to_western_digits(os.environ.get(PIN_VARIABLE, "")).strip()
    if not pin:
        pin = f"{secrets.randbelow(10000):04d}"
        print(f"PIN for the operator and supervisor pages (set {PIN_VARIABLE} in .env to choose your own): {pin}")
    return pin


# SIMULATED rows of the Elm view: other companies' replacement requests. Each is
# (company, label, hours left when the page is opened). All invented.
SIMULATED_REPLACEMENTS = [
    ("قوافل النور", "ع · طلب 1", 3.3),
    ("ضيوف الوادي", "ف · طلب 2", 11.0),
    ("ركب السلام", "ي · طلب 3", 19.7),
    ("قوافل النور", "ر · طلب 4", -1.2),
]


def problem(status: int, message: str) -> JSONResponse:
    return JSONResponse({"message": message}, status_code=status)


def create_app(engine=None, db_path: Path = DEFAULT_DB, now=datetime.now, replay=None, pin: str | None = None) -> FastAPI:
    """Builds the site. engine reads messages (app/engine.py); now() gives the time. Tests pass their own."""
    app = FastAPI(title="Rasd")
    store = Store(db_path)
    templates = Jinja2Templates(directory=HERE / "templates")
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    app.state.store = store
    app.state.last_voice = None  # how long the last voice note took, for the operator page
    app.state.operator_message = None  # what the operator's last button did, shown once

    # --- the PIN of the operator and supervisor pages -----------------------------------------------
    app.state.pin = pin if pin is not None else pin_for_this_run()
    pass_token = hashlib.sha256(f"{secrets.token_hex(16)}:{app.state.pin}".encode()).hexdigest()  # new at every start
    doors = {"wrong": 0, "shut_until": None}

    @app.middleware("http")
    async def ask_for_the_pin(request: Request, call_next):
        path = request.url.path
        locked = app.state.pin != PIN_OFF and any(path == p or path.startswith(p + "/") for p in PIN_PROTECTED)
        if locked and not hmac.compare_digest(request.cookies.get("rasd_pass", ""), pass_token):
            if path.startswith("/api/"):
                return problem(401, copy.PIN_NEEDED)
            return RedirectResponse(f"/pin?next={path}", status_code=303)
        return await call_next(request)

    def pin_page(request: Request, next: str, message: str | None = None, status: int = 200):
        target = next if next in ("/operator", "/supervisor") else "/operator"
        return templates.TemplateResponse(request, "pin.html", {"copy": copy, "next": target, "message": message}, status_code=status)

    @app.get("/pin", response_class=HTMLResponse)
    def pin_form(request: Request, next: str = "/operator"):
        return pin_page(request, next)

    @app.post("/pin", response_class=HTMLResponse)
    def pin_entered(request: Request, pin: str = Form(""), next: str = Form("/operator")):
        moment = now()
        if doors["shut_until"] and moment < doors["shut_until"]:
            return pin_page(request, next, copy.PIN_LOCKED, 429)
        if not hmac.compare_digest(to_western_digits(pin).strip().encode(), app.state.pin.encode()):
            doors["wrong"] += 1
            if doors["wrong"] >= PIN_TRIES:
                doors["wrong"], doors["shut_until"] = 0, moment + timedelta(seconds=PIN_LOCK_SECONDS)
                return pin_page(request, next, copy.PIN_LOCKED, 429)
            return pin_page(request, next, copy.PIN_WRONG, 401)
        doors["wrong"], doors["shut_until"] = 0, None
        response = RedirectResponse(next if next in ("/operator", "/supervisor") else "/operator", status_code=303)
        response.set_cookie("rasd_pass", pass_token, httponly=True, samesite="lax")
        return response

    def live_engine():
        nonlocal engine
        if engine is None:  # made on first use, so the pages open even before a key is set
            from app.engine import LiveEngine

            engine = LiveEngine()
        return engine

    def replay_engine():
        nonlocal replay
        if replay is None:
            from app.engine import ReplayEngine

            replay = ReplayEngine(otherwise=live_engine)
        return replay

    def mode() -> str:
        return store.setting("mode", "live")

    def the_engine():
        """The engine the operator's switch points at."""
        return replay_engine() if mode() == "replay" else live_engine()

    def page(request: Request, name: str, **values) -> HTMLResponse:
        return templates.TemplateResponse(request, name, {"copy": copy, **values})

    def board_view() -> dict:
        moment = now()
        cases = store.board(moment)
        columns = {state: [case for case in cases if case["state"] == state] for state in copy.STATES}
        return {
            "cases": cases, "columns": columns, "notifications": store.notifications(), "now": moment.isoformat(),
            "replay_mode": mode() == "replay", "refresh_ms": BOARD_REFRESH_SECONDS * 1000,
        }  # fmt: skip

    # --- reports coming in -------------------------------------------------------------------

    def receive(text: str, hotel: str, photo: bool, source: str) -> dict:
        """One message becomes a report in a case (app/intake.py), and the sender gets an answer."""
        def read(safe_text, photo_attached=False):  # the engine is built here, so a failure to build it is caught too
            return the_engine().read(safe_text, photo_attached=photo_attached)

        report_id, case_id, joined, report = take_in(store, read, text, hotel, photo, source, now())
        return answer_for(report_id, case_id, report, joined)

    def hear(audio: bytes, filename: str, hotel: str, source: str):
        """A voice note becomes words, then a report. Says how long each part took."""
        if len(audio) > MAX_AUDIO_BYTES:
            return problem(413, copy.AUDIO_TOO_LARGE)
        started = time.perf_counter()
        try:
            heard = the_engine().transcribe(audio, filename)
        except Exception as e:  # VoiceError, or anything else: the sender is told to type instead
            log.warning("voice note not written down (%s: %s)", type(e).__name__, e if isinstance(e, VoiceError) else "")
            return problem(503, copy.VOICE_FAILED)
        if not heard.strip():
            return problem(400, copy.EMPTY_MESSAGE)
        heard_at = time.perf_counter()
        reply = receive(heard, hotel, False, source=source)
        done = time.perf_counter()
        took = {"heard": round(heard_at - started, 2), "read": round(done - heard_at, 2), "total": round(done - started, 2)}
        app.state.last_voice = took
        return {**reply, "heard": redact(heard)[0], "seconds": took}

    def identify(case_id: int, image: bytes, media_type: str):
        """Identification: the MOCK card is read, then the simulated Elm lookup is asked. The photo is not kept."""
        if len(image) > MAX_PHOTO_BYTES:
            return problem(413, copy.PHOTO_TOO_LARGE)
        if not store.is_open_lost_pilgrim(case_id):
            return problem(409, copy.CARD_ONLY_FOR_LOST)
        try:
            engine_now = the_engine()
            reading = engine_now.read_card(image, media_type)
        except Exception as e:  # a dropped network must not show the sender an error page
            log.warning("card not read (%s)", type(e).__name__)
            reading = None
        if reading is None:
            return problem(422, copy.CARD_REFUSED)
        record = engine_now.elm.lookup(reading.full_name, reading.visa_number)
        if record is None:
            return problem(404, copy.NOT_IN_LOOKUP)
        try:
            notification = store.identify(case_id, reading.full_name, reading.visa_number, record, now())
        except NoSuchCase:
            return problem(404, copy.NOT_FOUND)
        found = copy.identified(record.company, record.hotel, record.room, record.supervisor)
        return {"identified": True, "message": found, "notification": notification}

    def answer_for(report_id: int, case_id: int | None, report, joined: bool = False) -> dict:
        """What the sender is told about a report."""
        question = ask_back(report)
        if case_id is None:
            message = copy.NOT_A_REPORT
        elif joined:
            count = next(case["count"] for case in store.board(now()) if case["id"] == case_id)
            message = copy.merged(case_id, count)
        else:
            place = copy.place_text(report.hotel, report.loc_kind, report.loc_number)
            message = copy.received(f"البلاغ {report_id}", report.type, place, report.owner, report.urgency)
            if report.needs_confirmation and question is None:
                message += " " + copy.SENT_TO_SUPERVISOR
        return {
            "report_id": report_id,
            "case_id": case_id,
            "merged": joined,
            "message": message,
            "type": report.type,
            "question": {"text": question.text, "options": list(question.options)} if question else None,
        }

    @app.post("/api/reports")
    def send_report(text: str = Form(""), hotel: str = Form(""), pilgrim_photo: UploadFile | None = File(None)):
        photo = pilgrim_photo is not None and bool(pilgrim_photo.filename)  # only THAT a photo came is kept
        if photo and len(pilgrim_photo.file.read(MAX_PHOTO_BYTES + 1)) > MAX_PHOTO_BYTES:
            return problem(413, copy.PHOTO_TOO_LARGE)
        if not text.strip() and not photo:
            return problem(400, copy.EMPTY_MESSAGE)
        return receive(text, hotel, photo, source="text")

    @app.post("/api/voice")
    def send_voice(hotel: str = Form(""), audio: UploadFile = File(...)):
        return hear(audio.file.read(), audio.filename or "note", hotel, source="voice")

    @app.post("/api/reports/{report_id}/answer")
    def answer_question(report_id: int, reply: str = Form("")):
        try:
            report, case_id, joined = store.answer_question(report_id, reply, now())
        except NothingToAnswer:
            return problem(409, copy.ALREADY_ANSWERED)
        except NoSuchCase:
            return problem(404, copy.NOT_FOUND)
        return answer_for(report_id, case_id, report, joined)

    @app.post("/api/cases/{case_id}/card")
    def show_card(case_id: int, photo: UploadFile = File(...)):
        return identify(case_id, photo.file.read(), photo.content_type or "image/png")

    # --- what people do to a case ----------------------------------------------------------------

    def act(action, case_id: int, who: str):
        if not who.strip():
            return problem(400, copy.NAME_NEEDED)
        try:
            action(case_id, who.strip(), now())
        except CaseClosed:
            return problem(409, copy.ALREADY_CLOSED)
        except NoSuchCase:
            return problem(404, copy.NOT_FOUND)
        return {"ok": True}

    @app.post("/api/cases/{case_id}/acknowledge")
    def acknowledge(case_id: int, who: str = Form("")):
        return act(store.acknowledge, case_id, who)

    @app.post("/api/cases/{case_id}/close")
    def close(case_id: int, who: str = Form("")):
        return act(store.close, case_id, who)

    @app.post("/api/cases/{case_id}/confirm")
    def confirm(case_id: int, who: str = Form("")):
        return act(store.confirm, case_id, who)

    @app.get("/api/cases/{case_id}/events")
    def events(case_id: int):
        return {"events": store.events(case_id)}

    @app.get("/api/cases/{case_id}/replacement")
    def replacement(case_id: int):
        request = store.replacement(case_id)
        return request if request else problem(404, copy.NOT_FOUND)

    @app.get("/cases/{case_id}/replacement", response_class=HTMLResponse)
    def replacement_page(request: Request, case_id: int):
        """The replacement request, filled in from the report. Numbers are never shown, only that we hold them."""
        saved = store.replacement(case_id)
        if not saved:
            return HTMLResponse(copy.NOT_FOUND, status_code=404)
        items = []
        for item in CHECKLISTS["nusuk_card"]:
            if item in saved["missing"]:
                items.append((item, copy.ITEM_MISSING))
            else:
                items.append((item, copy.NUMBER_KEPT if item.startswith("رقم") else copy.ITEM_PRESENT))
        return page(request, "replacement.html", request_for=saved, items=items, now=now().isoformat())

    # --- the board ------------------------------------------------------------------------------------

    @app.get("/api/board")
    def board_data():
        view = board_view()
        return {"cases": view["cases"], "notifications": view["notifications"], "now": view["now"]}

    @app.get("/board", response_class=HTMLResponse)
    def board_page(request: Request):
        return page(request, "board.html", **board_view())

    @app.get("/board/fragment", response_class=HTMLResponse)
    def board_fragment(request: Request):
        return page(request, "board_fragment.html", **board_view())

    # --- the Elm view: SIMULATED -------------------------------------------------------------------------

    def elm_requests() -> list[dict]:
        moment = now()
        simulated = [
            {
                "company": company,
                "label": label,
                "due_at": (moment + timedelta(hours=hours)).isoformat(timespec="seconds"),
                "live": False,
                "simulated": True,
            }
            for company, label, hours in SIMULATED_REPLACEMENTS
        ]
        return sorted(store.replacements() + simulated, key=lambda row: row["due_at"])

    @app.get("/api/elm")
    def elm_data():
        return {"simulated": True, "requests": elm_requests(), "now": now().isoformat()}

    @app.get("/elm", response_class=HTMLResponse)
    def elm_page(request: Request):
        return page(request, "elm.html", requests=elm_requests(), now=now().isoformat())

    @app.get("/elm/mockup", response_class=HTMLResponse)
    def elm_mockup(request: Request):
        return page(request, "elm_mockup.html")

    @app.post("/simulated-elm/lookup")
    async def simulated_elm_lookup(request: Request):
        """The simulated Elm service on its own address. It answers from invented records only."""
        try:
            body = await request.json()
        except ValueError:
            body = None
        if not isinstance(body, dict):
            return JSONResponse({"simulated": True, "error": "send a JSON object with name and visa_number"}, status_code=400)
        record = SimulatedElm().lookup(str(body.get("name", "")), str(body.get("visa_number", "")))
        if record is None:
            return {"simulated": True, "found": False}
        return {
            "simulated": True, "found": True, "company": record.company, "hotel": record.hotel,
            "room": record.room, "supervisor": record.supervisor,
        }  # fmt: skip

    # --- the operator: the replay switch, the saved scene, clearing the board ---------------------------

    def scene_plays(files) -> bool:
        """True when every saved file is there AND the replay engine can be built from them."""
        if not all((scene.SCENE_DIR / name).exists() for name in files):
            return False
        try:
            from app.engine import ReplayEngine

            saved = ReplayEngine()
            return all(words in saved.readings for words in (scene.COUNTER_NOTE, scene.PILGRIM_NOTE))
        except Exception:
            return False

    def checks() -> list[dict]:
        """What the demo needs, looked at without calling anything outside this laptop."""
        load_dotenv(PROJECT_DIR / ".env")
        files = (scene.COUNTER_FILE, scene.PILGRIM_FILE, scene.CARD_FILE, "transcripts.json", "saved_readings.json")
        found = [
            ("claude_key", bool(os.environ.get(KEY_VARIABLE, "").strip()), copy.CHECK_CLAUDE_KEY_OK, copy.CHECK_CLAUDE_KEY_MISSING),
            ("speech_key", bool(os.environ.get(OPENAI_KEY_VARIABLE, "").strip()), copy.CHECK_SPEECH_KEY_OK, copy.CHECK_SPEECH_KEY_MISSING),
            ("saved_scene", scene_plays(files), copy.CHECK_SCENE_OK, copy.CHECK_SCENE_MISSING),
        ]  # fmt: skip
        return [{"name": name, "ok": ok, "text": good if ok else bad} for name, ok, good, bad in found]

    def set_mode(wanted: str):
        if wanted not in MODES:
            return problem(400, copy.UNKNOWN_MODE)
        store.set_setting("mode", wanted)
        return {"mode": wanted}

    def play(step: str):
        """Sends one saved file of the scene as if it had just arrived."""
        if step == "counter":
            return hear((scene.SCENE_DIR / scene.COUNTER_FILE).read_bytes(), scene.COUNTER_FILE, scene.REPORTING_HOTEL, SAVED_SOURCE)
        if step == "pilgrim":
            return hear((scene.SCENE_DIR / scene.PILGRIM_FILE).read_bytes(), scene.PILGRIM_FILE, scene.REPORTING_HOTEL, SAVED_SOURCE)
        if step == "card":
            case_id = store.open_lost_pilgrim_case()
            if case_id is None:
                return problem(409, copy.NO_CASE_FOR_CARD)
            return identify(case_id, (scene.SCENE_DIR / scene.CARD_FILE).read_bytes(), "image/png")
        return problem(404, copy.NOT_FOUND)

    def clear(confirm: str):
        if confirm != "yes":
            return problem(400, copy.CLEAR_NEEDS_YES)
        store.clear()
        return {"ok": True, "message": copy.CLEARED}

    def said(result) -> str:
        """The Arabic sentence inside a reply, whether it is a plain answer or a problem."""
        body = json.loads(result.body) if isinstance(result, JSONResponse) else result
        return body.get("message") or (copy.MODE_REPLAY if body.get("mode") == "replay" else copy.MODE_LIVE)

    @app.get("/api/operator/status")
    def operator_status():
        return {"mode": mode(), "last_voice": app.state.last_voice, "checks": checks()}

    @app.post("/api/operator/mode")
    def operator_mode(mode: str = Form("")):
        return set_mode(mode)

    @app.post("/api/operator/scene/{step}")
    def operator_scene(step: str):
        return play(step)

    @app.post("/api/operator/reset")
    def operator_reset(confirm: str = Form("")):
        return clear(confirm)

    # The operator page itself uses plain forms, so it works on any phone browser, with no script.
    @app.get("/operator", response_class=HTMLResponse)
    def operator_page(request: Request):
        message, app.state.operator_message = app.state.operator_message, None
        return page(
            request, "operator.html", mode=mode(), last_voice=app.state.last_voice, checks=checks(), message=message
        )

    def back_to_operator(result):
        app.state.operator_message = said(result)
        return RedirectResponse("/operator", status_code=303)

    @app.post("/operator/mode")
    def operator_mode_form(mode: str = Form("")):
        return back_to_operator(set_mode(mode))

    @app.post("/operator/scene/{step}")
    def operator_scene_form(step: str):
        return back_to_operator(play(step))

    @app.post("/operator/reset")
    def operator_reset_form(confirm: str = Form("")):
        return back_to_operator(clear(confirm))

    @app.get("/supervisor", response_class=HTMLResponse)
    def supervisor_page(request: Request):
        """What waits for the supervisor, with the text of each message (numbers hidden). Not for the big screen."""
        return page(request, "supervisor.html", waiting=store.waiting(now()))

    @app.get("/scenario-card", response_class=HTMLResponse)
    def scenario_card(request: Request):
        return page(request, "scenario_card.html", scene=scene)

    # --- the other pages ------------------------------------------------------------------------------------

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request):
        return page(request, "index.html", hotels=HOTELS)

    @app.get("/report", response_class=HTMLResponse)
    def report_page(request: Request, hotel: str = ""):
        return page(request, "report.html", hotel=listed_hotel(hotel) or "", hotels=HOTELS)

    @app.post("/report", response_class=HTMLResponse)
    def report_plain_form(
        request: Request,
        text: str = Form(""),
        hotel: str = Form(""),
        pilgrim_photo: UploadFile | None = File(None),
        audio: UploadFile | None = File(None),
    ):
        """The same page for a phone whose browser runs no script: a plain form, and the answer in the page."""
        photo = pilgrim_photo is not None and bool(pilgrim_photo.filename)
        if audio is not None and audio.filename:
            result = hear(audio.file.read(), audio.filename, hotel, source="voice")
        elif text.strip() or photo:
            result = receive(text, hotel, photo, source="text")
        else:
            result = problem(400, copy.EMPTY_MESSAGE)
        body = json.loads(result.body) if isinstance(result, JSONResponse) else result
        question = body.get("question") or {}
        return page(
            request, "report.html", hotel=listed_hotel(hotel) or "", hotels=HOTELS,
            reply=body.get("message"), heard=body.get("heard"), question=question.get("text"),
        )  # fmt: skip

    @app.get("/before-after", response_class=HTMLResponse)
    def before_after(request: Request):
        scene = json.loads(BEFORE_AFTER_FILE.read_text(encoding="utf-8")) if BEFORE_AFTER_FILE.exists() else {"messages": [], "cases": []}
        return page(request, "before_after.html", scene=scene)

    return app


def __getattr__(name: str):
    """`uvicorn app.main:app` builds the live site on first use (it needs the Claude key)."""
    if name == "app":
        return create_app()
    raise AttributeError(name)
