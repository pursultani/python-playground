"""Screenshot scenes for looking at the page. Images go to a temp folder, never into the repo."""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

import pytest
from fake_host import FakeHost
from page_driver import App, create, error, frame, print_, status

SHOTS = Path(
    os.environ.get(
        "PLAYGROUND_SHOTS",
        "/private/var/folders/mm/y6zzp5q160n30k0hz12tgp7m0000gn/T/opencode/shots",
    )
)

SCENE = [
    create(1, "grid", color="lightgray", width=1, size=50, style="solid"),
    create(2, "axis", color="gray", width=3, size=100, style="solid", labels=True),
    create(3, "circle", x=-250, y=150, radius=60, color="steelblue", title="Circle"),
    create(
        4,
        "rectangle",
        x=-60,
        y=150,
        width=170,
        height=100,
        color="tomato",
        rotation=15,
        title="Rectangle",
    ),
    create(5, "triangle", x=200, y=150, width=120, height=120, color="gold", title="Triangle"),
    create(6, "line", x=-300, y=-60, x2=-100, y2=-200, width=6, color="seagreen", title="Line"),
    create(7, "text", x=100, y=-100, text="Hello 🌍", size=48, color="purple"),
    create(8, "circle", x=250, y=-150, radius=40, color="orange", opacity=0.5, title="50%"),
    create(9, "triangle", x=0, y=-150, width=90, height=80, color="hotpink", rotation=90),
    create(10, "circle", x=0, y=0, radius=12, color="black", visible=False),
]


@pytest.fixture(autouse=True)
def _shots_dir() -> None:
    SHOTS.mkdir(parents=True, exist_ok=True)


def shot(app: App, name: str) -> None:
    app.page.wait_for_timeout(350)
    app.page.screenshot(path=str(SHOTS / f"{name}.png"))


def test_every_shape(app: App) -> None:
    app.send(frame(*SCENE), print_("Hello!\n"), print_("score = 3\n"))
    app.page.wait_for_selector("#shapes > g[data-id='9']", state="attached")
    shot(app, "scene")


def test_small_and_normal_guides(open_app: Callable[..., App]) -> None:
    for name, guides in {
        "grid_5": [create(1, "grid", size=5)],
        "axis_10": [create(1, "axis", size=10)],
        "guides_normal": [create(1, "grid", size=50), create(2, "axis", size=100)],
    }.items():
        app = open_app()
        app.send(frame(*guides))
        app.sync()
        shot(app, name)


def test_error_panel(app: App) -> None:
    app.send(
        frame(*SCENE),
        print_("starting...\n"),
        error(
            frames=[
                {
                    "file": "main.py",
                    "line": 12,
                    "function": "<module>",
                    "code": "go()",
                    "col": 1,
                    "end_col": 3,
                },
                {
                    "file": "main.py",
                    "line": 8,
                    "function": "go",
                    "code": "    bal.x += 1",
                    "col": 5,
                    "end_col": 8,
                },
            ],
            context=[
                {"line": 6, "code": "def go():"},
                {"line": 7, "code": "    ball = Circle()"},
                {"line": 8, "code": "    bal.x += 1"},
            ],
        ),
        {"t": "status", "run": 1, "state": "crashed"},
    )
    app.page.wait_for_selector("#error-panel:not([hidden])")
    shot(app, "error")


def test_dark_and_narrow(open_app: Callable[..., App]) -> None:
    app = open_app(color_scheme="dark", viewport={"width": 1000, "height": 760})
    app.send(frame(*SCENE), print_("Hello!\n"), print_("Oops, something is wrong\n", "stderr"))
    app.page.wait_for_selector("#shapes > g[data-id='9']", state="attached")
    shot(app, "dark")
    narrow = open_app(viewport={"width": 390, "height": 720})
    narrow.send(frame(*SCENE), print_("Hello!\n"))
    narrow.page.wait_for_selector("#shapes > g[data-id='9']", state="attached")
    shot(narrow, "narrow")


def test_console_stderr_and_states(app: App) -> None:
    app.send(
        print_("Hello!\n"),
        print_("Traceback-ish text\n", "stderr"),
        frame(create(1, "circle", x=0, y=0, radius=80, color="steelblue")),
        status("finished"),
    )
    app.expect_state("finished")
    shot(app, "finished")


def test_error_dark_narrow_and_banner(open_app: Callable[..., App], host: FakeHost) -> None:
    host.retry_ms = 10_000
    app = open_app(color_scheme="dark", viewport={"width": 420, "height": 760})
    app.send(
        frame(*SCENE),
        error(
            "SyntaxError",
            "'(' was never closed",
            frames=[
                {
                    "file": "main.py",
                    "line": 2,
                    "function": "<module>",
                    "code": "ball = Circle(x=10, y=20",
                    "col": 14,
                    "end_col": 15,
                }
            ],
            context=[
                {"line": 1, "code": "# my first program"},
                {"line": 2, "code": "ball = Circle(x=10, y=20"},
                {"line": 3, "code": "ball.color = 'red'"},
            ],
        ),
        status("crashed"),
    )
    app.page.wait_for_selector("#error-panel:not([hidden])")
    shot(app, "error_dark_narrow")
    app.host.drop_clients()
    app.page.wait_for_selector("#banner:not([hidden])")
    app.page.screenshot(path=str(SHOTS / "banner.png"))


def test_console_collapsed(app: App) -> None:
    app.send(frame(*SCENE), print_("hi\n"))
    app.page.click("#console-toggle")
    shot(app, "collapsed")
