"""Clicks and keys sent back to the host."""

from __future__ import annotations

from typing import Any

from page_driver import App, create, frame, print_, status


def wait_events(app: App, count: int) -> list[dict[str, Any]]:
    for _ in range(100):
        if len(app.host.events) >= count:
            break
        app.page.wait_for_timeout(30)
    return list(app.host.events)


def settle(app: App) -> None:
    app.page.wait_for_timeout(150)


def canvas_point(app: App, x: float, y: float) -> tuple[float, float]:
    """Page pixel position of logical canvas point (x, y)."""
    box = app.page.locator("#canvas-wrap").bounding_box()
    assert box is not None
    scale = box["width"] / 800
    return box["x"] + box["width"] / 2 + x * scale, box["y"] + box["height"] / 2 - y * scale


def test_click_on_empty_canvas(app: App) -> None:
    px, py = canvas_point(app, 100, 50)
    app.page.mouse.click(px, py)
    events = wait_events(app, 1)
    assert len(events) == 1
    event = events[0]
    assert event["t"] == "click"
    assert event["target"] is None
    assert abs(event["x"] - 100) <= 1
    assert abs(event["y"] - 50) <= 1


def test_click_reports_target_id(app: App) -> None:
    app.send(
        frame(
            create(1, "circle", x=-200, y=0, radius=40, title="hit"),
            create(2, "rectangle", x=200, y=100, width=100, height=60),
            create(3, "grid"),
        )
    )
    app.sync()
    app.page.mouse.click(*canvas_point(app, 200, 100))
    app.page.mouse.click(*canvas_point(app, -200, 0))
    app.page.mouse.click(*canvas_point(app, 0, -200))
    events = wait_events(app, 3)
    assert [e["target"] for e in events] == [2, 1, None]
    assert events[1]["x"] in range(-202, -197)
    assert events[1]["y"] in range(-2, 3)


def test_click_on_title_counts_as_click_on_the_shape(app: App) -> None:
    app.send(frame(create(7, "circle", x=0, y=0, radius=50, title="label")))
    app.sync()
    app.page.mouse.click(*canvas_point(app, 0, 0))
    assert wait_events(app, 1)[0]["target"] == 7


def test_click_outside_canvas_is_ignored(app: App) -> None:
    app.page.mouse.click(5, 70)
    settle(app)
    assert app.host.events == []


def test_events_not_sent_unless_running(app: App) -> None:
    for state in ("starting", "finished", "crashed"):
        app.send(status(state))
        app.expect_state(state)
        app.page.mouse.click(*canvas_point(app, 0, 0))
        app.page.keyboard.press("a")
    settle(app)
    assert app.host.events == []
    app.send(status("running"))
    app.expect_state("running")
    app.page.keyboard.press("a")
    assert wait_events(app, 1) == [{"t": "key", "key": "a"}]


def test_keys(app: App) -> None:
    for key in ["a", "A", "ArrowLeft", "Enter", "Escape", "Space", "1"]:
        app.page.keyboard.press(key)
    events = wait_events(app, 7)
    assert [e["key"] for e in events] == [
        "a",
        "A",
        "ArrowLeft",
        "Enter",
        "Escape",
        "Space",
        "1",
    ]
    assert all(e["t"] == "key" for e in events)


def test_key_repeats_are_sent(app: App) -> None:
    app.page.keyboard.down("ArrowRight")
    app.page.keyboard.down("ArrowRight")
    app.page.keyboard.up("ArrowRight")
    assert len(wait_events(app, 2)) == 2


def test_modifier_combinations_are_not_forwarded(app: App) -> None:
    for combo in ["Control+a", "Alt+a", "Meta+a"]:
        app.page.keyboard.press(combo)
    app.page.keyboard.press("b")
    wait_events(app, 1)
    settle(app)
    keys = [e["key"] for e in app.host.events if e["key"] not in ("Control", "Alt", "Meta")]
    assert keys == ["b"]


def test_arrows_and_space_do_not_scroll_the_page(app: App) -> None:
    prevented = app.page.evaluate(
        """() => ["ArrowDown", "ArrowUp", " ", "a"].map((key) => {
            const e = new KeyboardEvent("keydown", { key, cancelable: true, bubbles: true });
            window.dispatchEvent(e);
            return e.defaultPrevented;
        })"""
    )
    assert prevented == [True, True, True, False]


def test_space_on_a_focused_button_is_left_alone(app: App) -> None:
    app.page.focus("#restart")
    app.page.keyboard.press("Space")
    settle(app)
    assert app.host.events == []


def fill_console(app: App, lines: int = 200) -> None:
    app.send(print_("".join(f"line {i}\n" for i in range(lines))))
    app.sync()


def test_keys_in_the_console_scroll_it_and_are_not_sent_to_the_program(app: App) -> None:
    fill_console(app)
    app.page.locator("#console").evaluate("e => { e.scrollTop = 0; }")
    app.page.focus("#console")
    prevented = app.page.evaluate(
        """() => ["ArrowDown", " ", "ArrowUp"].map((key) => {
            const e = new KeyboardEvent("keydown", { key, cancelable: true, bubbles: true });
            document.getElementById("console").dispatchEvent(e);
            return e.defaultPrevented;
        })"""
    )
    assert prevented == [False, False, False]
    app.page.keyboard.press("ArrowDown")
    app.page.keyboard.press("PageDown")
    app.page.keyboard.press("Space")
    app.page.wait_for_function("document.getElementById('console').scrollTop > 0")
    settle(app)
    assert app.host.events == []


def test_clicking_the_console_then_the_canvas_gives_keys_back_to_the_program(app: App) -> None:
    fill_console(app, 5)
    app.page.click("#console")
    app.page.keyboard.press("a")
    settle(app)
    assert app.host.events == []
    app.page.mouse.click(*canvas_point(app, 0, 0))
    app.page.keyboard.press("b")
    keys = [e for e in wait_events(app, 2) if e["t"] == "key"]
    assert keys == [{"t": "key", "key": "b"}]


def test_arrows_on_a_focused_button_are_left_alone(app: App) -> None:
    app.page.focus("#restart")
    prevented = app.page.evaluate(
        """() => {
            const e = new KeyboardEvent("keydown", {
                key: "ArrowLeft", cancelable: true, bubbles: true,
            });
            document.getElementById("restart").dispatchEvent(e);
            return e.defaultPrevented;
        }"""
    )
    assert prevented is False
    app.page.keyboard.press("ArrowRight")
    settle(app)
    assert app.host.events == []


def test_clicking_console_buttons_does_not_steal_later_keys(app: App) -> None:
    app.page.click("#console-clear")
    app.page.keyboard.press("ArrowUp")
    app.page.click("#console-toggle")
    app.page.keyboard.press("Space")
    events = wait_events(app, 2)
    assert [e["key"] for e in events] == ["ArrowUp", "Space"]


def test_clicking_restart_does_not_steal_later_keys(app: App) -> None:
    app.page.click("#restart")
    app.page.keyboard.press("Space")
    assert wait_events(app, 1) == [{"t": "key", "key": "Space"}]
