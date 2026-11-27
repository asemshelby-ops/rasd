"""End-to-end browser tests of the demo pages, with Playwright. Not part of the everyday run:

    python -m pytest -m e2e -q

The app runs on a free local port with the PIN off (tests/conftest.py) and the
operator's switch on replay, so only the saved scene is used. Nothing may leave
this computer: the browser aborts every request to another address, Python
refuses every outside connection, and the live engine is replaced by one that
records any call. Each of the three ends the test with an error.
"""

import importlib.util
import socket
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

if importlib.util.find_spec("playwright") is None:  # not installed: the browser tests are simply not collected
    collect_ignore_glob = ["test_*.py"]

SCREENSHOTS = Path(__file__).resolve().parents[2] / "results" / "e2e"
LOOPBACK = {"127.0.0.1", "::1", "localhost"}


class NoPaidCalls:
    """Stands where the live engine would be. Replay mode falls back to it for anything not in the saved scene."""

    def __init__(self):
        self.asked = []

    def _refuse(self, what):
        self.asked.append(what)
        raise RuntimeError(f"e2e: the live engine was asked to {what}")

    def read(self, text, photo_attached=False):
        self._refuse("read a message")

    def transcribe(self, audio, filename):
        self._refuse("transcribe a voice note")

    def read_card(self, image, media_type):
        self._refuse("read a card")


@pytest.fixture(scope="session")
def outside_tries():
    """Python in this process may connect to this computer only. Every other try is refused and listed."""
    tried = []
    real = socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo

    def outside(family, address) -> bool:
        return family in (socket.AF_INET, socket.AF_INET6) and str(address[0]) not in LOOPBACK

    def connect(self, address):
        if outside(self.family, address):
            tried.append(address)
            raise ConnectionRefusedError(f"e2e: blocked a connection to {address}")
        return real[0](self, address)

    def connect_ex(self, address):
        if outside(self.family, address):
            tried.append(address)
            return 111
        return real[1](self, address)

    def getaddrinfo(host, *args, **kwargs):
        if host is not None and str(host) not in LOOPBACK:
            tried.append(host)
            raise socket.gaierror(f"e2e: blocked a name lookup of {host}")
        return real[2](host, *args, **kwargs)

    socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo = connect, connect_ex, getaddrinfo
    yield tried
    socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo = real


@pytest.fixture
def site(tmp_path, outside_tries):
    """The app on a free port of 127.0.0.1, with its own empty database."""
    import uvicorn

    from app.main import create_app

    engine = NoPaidCalls()
    app = create_app(engine=engine, db_path=tmp_path / "e2e.db")
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    server = uvicorn.Server(uvicorn.Config(app, log_level="warning"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        assert time.monotonic() < deadline, "the app did not start"
        time.sleep(0.05)
    tries_before = len(outside_tries)
    yield SimpleNamespace(url=f"http://127.0.0.1:{listener.getsockname()[1]}", engine=engine)
    server.should_exit = True
    thread.join(10)
    assert not engine.asked, f"the live engine was asked: {engine.asked}"
    assert len(outside_tries) == tries_before, f"Python tried to leave this computer: {outside_tries[tries_before:]}"


@pytest.fixture(scope="session")
def browser():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        chromium = playwright.chromium.launch()
        yield chromium
        chromium.close()


@pytest.fixture
def open_page(browser, site):
    """open_page(path, width, height, phone=False) opens a page in its own browser context, which may reach only the app."""
    contexts, left = [], []

    def only_this_app(route):
        if route.request.url.startswith(site.url + "/"):
            route.continue_()
        else:
            left.append(route.request.url)
            route.abort()

    def open_page(path, width=1280, height=800, phone=False):
        context = browser.new_context(viewport={"width": width, "height": height}, is_mobile=phone, has_touch=phone)
        context.route("**/*", only_this_app)
        contexts.append(context)
        page = context.new_page()
        page.goto(site.url + path)
        return page

    yield open_page
    for context in contexts:
        context.close()
    assert not left, f"the browser tried to leave this computer: {left}"


@pytest.fixture
def operator(open_page):
    """The operator page, with the switch turned to replay."""
    from playwright.sync_api import expect

    from app import copy

    page = open_page("/operator")
    page.get_by_role("button", name=copy.SWITCH_TO_REPLAY).click()
    expect(page.get_by_role("heading", name=copy.MODE_REPLAY)).to_be_visible()
    return page


@pytest.fixture(scope="session")
def screenshots():
    SCREENSHOTS.mkdir(parents=True, exist_ok=True)
    return SCREENSHOTS
