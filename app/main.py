"""The pages of the demo: the reporting page, the board, the Elm view and the before-and-after page.

    uvicorn app.main:app --host 0.0.0.0 --port 8000

FastAPI, one SQLite file, plain HTML pages, no build step. The rules live in
rasd/; this file only receives requests, calls the rules and shows the result.

What the big screen may show is decided in app/store.py (Store.board): no full
name, no passport or visa number, no words of a message, no photo.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import copy
from app.intake import take_in
from app.store import CaseClosed, NoSuchCase, NothingToAnswer, Store
from rasd.askback import ask_back
from rasd.privacy import redact
from rasd.routing import CHECKLISTS, HOTELS, match_hotel
from rasd.voice import VoiceError

HERE = Path(__file__).resolve().parent
PROJECT_DIR = HERE.parent
DEFAULT_DB = PROJECT_DIR / "rasd.db"
BEFORE_AFTER_FILE = PROJECT_DIR / "demo" / "before_after.json"

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


def create_app(engine=None, db_path: Path = DEFAULT_DB, now=datetime.now) -> FastAPI:
    """Builds the site. engine reads messages (app/engine.py); now() gives the time. Tests pass their own."""
    app = FastAPI(title="Rasd")
    store = Store(db_path)
    templates = Jinja2Templates(directory=HERE / "templates")
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    app.state.store = store

    def the_engine():
        nonlocal engine
        if engine is None:  # made on first use, so the pages open even before a key is set
            from app.engine import LiveEngine

            engine = LiveEngine()
        return engine

    def page(request: Request, name: str, **values) -> HTMLResponse:
        return templates.TemplateResponse(request, name, {"copy": copy, **values})

    def board_view() -> dict:
        moment = now()
        cases = store.board(moment)
        columns = {state: [case for case in cases if case["state"] == state] for state in copy.STATES}
        return {"cases": cases, "columns": columns, "notifications": store.notifications(), "now": moment.isoformat()}

    # --- reports coming in -------------------------------------------------------------------

    def receive(text: str, hotel: str, photo: bool, source: str) -> dict:
        """One message becomes a report in a case (app/intake.py), and the sender gets an answer."""
        report_id, case_id, joined, report = take_in(store, the_engine().read, text, hotel, photo, source, now())
        return answer_for(report_id, case_id, report, joined)

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
    async def send_report(text: str = Form(""), hotel: str = Form(""), pilgrim_photo: UploadFile | None = File(None)):
        photo = pilgrim_photo is not None and bool(pilgrim_photo.filename)  # only THAT a photo came is kept
        if not text.strip() and not photo:
            return problem(400, copy.EMPTY_MESSAGE)
        return receive(text, hotel, photo, source="text")

    @app.post("/api/voice")
    async def send_voice(hotel: str = Form(""), audio: UploadFile = File(...)):
        try:
            heard = the_engine().transcribe(await audio.read(), audio.filename or "note")
        except VoiceError:
            return problem(503, copy.VOICE_FAILED)
        if not heard.strip():
            return problem(400, copy.EMPTY_MESSAGE)
        return {**receive(heard, hotel, False, source="voice"), "heard": redact(heard)[0]}

    @app.post("/api/reports/{report_id}/answer")
    async def answer_question(report_id: int, reply: str = Form("")):
        try:
            report, case_id = store.answer_question(report_id, reply, now())
        except NothingToAnswer:
            return problem(409, copy.ALREADY_ANSWERED)
        except NoSuchCase:
            return problem(404, copy.NOT_FOUND)
        return answer_for(report_id, case_id, report)

    @app.post("/api/cases/{case_id}/card")
    async def show_card(case_id: int, photo: UploadFile = File(...)):
        """Identification: the MOCK card is read, then the simulated Elm lookup is asked. The photo is not kept."""
        reading = the_engine().read_card(await photo.read(), photo.content_type or "image/png")
        if reading is None:
            return problem(422, copy.CARD_REFUSED)
        record = the_engine().elm.lookup(reading.full_name, reading.visa_number)
        if record is None:
            return problem(404, copy.NOT_IN_LOOKUP)
        try:
            notification = store.identify(case_id, reading.full_name, reading.visa_number, record, now())
        except NoSuchCase:
            return problem(404, copy.NOT_FOUND)
        found = copy.identified(record.company, record.hotel, record.room, record.supervisor)
        return {"identified": True, "message": found, "notification": notification}

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
    async def acknowledge(case_id: int, who: str = Form("")):
        return act(store.acknowledge, case_id, who)

    @app.post("/api/cases/{case_id}/close")
    async def close(case_id: int, who: str = Form("")):
        return act(store.close, case_id, who)

    @app.post("/api/cases/{case_id}/confirm")
    async def confirm(case_id: int, who: str = Form("")):
        return act(store.confirm, case_id, who)

    @app.get("/api/cases/{case_id}/events")
    async def events(case_id: int):
        return {"events": store.events(case_id)}

    @app.get("/api/cases/{case_id}/replacement")
    async def replacement(case_id: int):
        request = store.replacement(case_id)
        return request if request else problem(404, copy.NOT_FOUND)

    @app.get("/cases/{case_id}/replacement", response_class=HTMLResponse)
    async def replacement_page(request: Request, case_id: int):
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
    async def board_data():
        view = board_view()
        return {"cases": view["cases"], "notifications": view["notifications"], "now": view["now"]}

    @app.get("/board", response_class=HTMLResponse)
    async def board_page(request: Request):
        return page(request, "board.html", **board_view())

    @app.get("/board/fragment", response_class=HTMLResponse)
    async def board_fragment(request: Request):
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
    async def elm_data():
        return {"simulated": True, "requests": elm_requests(), "now": now().isoformat()}

    @app.get("/elm", response_class=HTMLResponse)
    async def elm_page(request: Request):
        return page(request, "elm.html", requests=elm_requests(), now=now().isoformat())

    @app.get("/elm/mockup", response_class=HTMLResponse)
    async def elm_mockup(request: Request):
        return page(request, "elm_mockup.html")

    @app.post("/simulated-elm/lookup")
    async def simulated_elm_lookup(request: Request):
        """The simulated Elm service on its own address. It answers from invented records only."""
        body = await request.json()
        record = the_engine().elm.lookup(str(body.get("name", "")), str(body.get("visa_number", "")))
        if record is None:
            return {"simulated": True, "found": False}
        return {
            "simulated": True, "found": True, "company": record.company, "hotel": record.hotel,
            "room": record.room, "supervisor": record.supervisor,
        }  # fmt: skip

    # --- the other pages ------------------------------------------------------------------------------------

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        return page(request, "index.html", hotels=HOTELS)

    @app.get("/report", response_class=HTMLResponse)
    async def report_page(request: Request, hotel: str = ""):
        return page(request, "report.html", hotel=match_hotel(hotel) or "", hotels=HOTELS)

    @app.get("/before-after", response_class=HTMLResponse)
    async def before_after(request: Request):
        scene = json.loads(BEFORE_AFTER_FILE.read_text(encoding="utf-8")) if BEFORE_AFTER_FILE.exists() else {"messages": [], "cases": []}
        return page(request, "before_after.html", scene=scene)

    return app


def __getattr__(name: str):
    """`uvicorn app.main:app` builds the live site on first use (it needs the Claude key)."""
    if name == "app":
        return create_app()
    raise AttributeError(name)
