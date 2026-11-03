"""Page chrome: status badge, snapshots, connection handling."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from page_driver import App, create, error, frame, print_, status
from playwright.sync_api import expect


def test_loads_with_title_and_script_name(app: App) -> None:
    assert app.page.title() == "Python Playground"
    expect(app.page.locator("#script-name")).to_have_text("main.py")
    expect(app.page.locator("#restart")).to_be_visible()
    assert app.page.evaluate("window.__playground.state") == "running"


@pytest.mark.parametrize(
    ("state", "text"),
    [
        ("starting", "Starting…"),
        ("running", "Running…"),
        ("finished", "Program finished ✓"),
        ("crashed", "Stopped by an error ✗"),
    ],
)
def test_status_badge(app: App, state: str, text: str) -> None:
    app.send(status("finished" if state == "starting" else "starting"))
    app.send(status(state))
    app.expect_state(state)
    expect(app.page.locator("#status")).to_have_text(text)
    expect(app.page.locator("#status")).to_have_attribute("data-state", state)


def test_run_number_is_exposed(app: App) -> None:
    app.send({"t": "run", "run": 7}, status("running", 7))
    expect(app.page.locator("body")).to_have_attribute("data-run", "7")


def test_snapshot_rebuilds_everything(open_app: Callable[..., App]) -> None:
    app = open_app(
        {
            "run": 3,
            "state": "finished",
            "background": "navy",
            "objects": [
                {"id": 1, "type": "circle", "props": {"x": 10, "y": 20, "radius": 30}},
                {"id": 2, "type": "text", "props": {"text": "Hi", "x": 0, "y": 0}},
            ],
            "console": [
                {"text": "hello\n", "stream": "stdout"},
                {"text": "oops\n", "stream": "stderr"},
            ],
            "error": None,
        }
    )
    app.expect_state("finished")
    assert app.ids() == [1, 2]
    expect(app.page.locator("#background")).to_have_attribute("fill", "navy")
    assert app.console_text() == "hello\noops\n"
    expect(app.page.locator("#console .stderr")).to_have_text("oops\n")
    expect(app.page.locator("#error-panel")).to_be_hidden()
    expect(app.page.locator("body")).to_have_attribute("data-run", "3")


def test_snapshot_with_error_shows_panel(open_app: Callable[..., App]) -> None:
    payload = error(
        "ValueError",
        "bad",
        frames=[{"file": "main.py", "line": 2, "function": "<module>", "code": "x"}],
        context=[{"line": 2, "code": "x"}],
    )
    app = open_app({"state": "crashed", "error": payload})
    expect(app.page.locator("#error-panel")).to_be_visible()
    expect(app.page.locator(".err-message")).to_have_text("bad")


def test_snapshot_replaces_existing_content_without_transitions(app: App) -> None:
    app.send(frame(create(1, "circle", x=0, y=0, radius=40), create(2, "circle", x=5, y=5)))
    app.send(print_("old\n"))
    app.sync()
    app.send(
        {
            "t": "snapshot",
            "run": 2,
            "state": "running",
            "script": "other.py",
            "background": "white",
            "objects": [{"id": 5, "type": "rectangle", "props": {"x": 1, "y": 1}}],
            "console": [],
            "error": None,
        }
    )
    app.sync()
    assert app.ids() == [5]
    expect(app.page.locator("#script-name")).to_have_text("other.py")
    assert app.console_text() == ""
    assert app.shape(5).evaluate("e => e.getAnimations().length") == 0


def test_disconnected_banner_and_reconnect(app: App) -> None:
    app.send(frame(create(1, "circle", x=0, y=0, radius=40)))
    app.sync()
    expect(app.page.locator("#banner")).to_be_hidden()

    app.host.snapshot = {
        **app.host.snapshot,
        "run": 2,
        "objects": [{"id": 1, "type": "rectangle", "props": {"x": 0, "y": 0}}],
        "console": [{"text": "after reconnect\n", "stream": "stdout"}],
    }
    app.host.drop_clients()
    expect(app.page.locator("#banner")).to_contain_text("Disconnected: waiting for the playground")
    # the page reconnects by itself and the next snapshot restores everything
    expect(app.page.locator("#banner")).to_be_hidden()
    expect(app.shape(1)).to_have_attribute("data-type", "rectangle")
    assert app.console_text() == "after reconnect\n"


def test_restart_button_posts(app: App) -> None:
    app.page.click("#restart")
    app.page.wait_for_function("true")
    for _ in range(50):
        if app.host.restarts:
            break
        app.page.wait_for_timeout(50)
    assert app.host.restarts == 1


def test_background_message_changes_canvas(app: App) -> None:
    app.send({"t": "canvas", "background": "black"})
    expect(app.page.locator("#background")).to_have_attribute("fill", "black")
