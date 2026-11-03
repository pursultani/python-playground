"""Real mouse clicks and key presses, from the browser all the way to student handlers."""

from __future__ import annotations

import re

from e2e_helpers import Playground, poll
from playwright.sync_api import expect

LOOP = "while True:\n    wait(0.02)\n"


def clicks(pg: Playground, prefix: str) -> list[tuple[int, int]]:
    return [(int(a), int(b)) for a, b in re.findall(rf"{prefix} (-?\d+) (-?\d+)", pg.console())]


def test_click_on_a_shape_calls_its_handler(pg: Playground):
    pg.start(
        "def hit(x, y):\n    print('shape', x, y)\n"
        "def miss(x, y):\n    print('canvas', x, y)\n"
        "ball = Circle(100, 100, radius=40, color='tomato')\n"
        "ball.on_click(hit)\n"
        "on_click(miss)\n" + LOOP
    )
    pg.wait_state("running")
    pg.click_at(100, 100)
    pg.wait_for_console("shape")
    (x, y) = clicks(pg, "shape")[0]
    assert abs(x - 100) <= 2 and abs(y - 100) <= 2
    assert "canvas" not in pg.console(), "a handled shape must not also call the canvas handler"


def test_click_on_empty_canvas_calls_the_canvas_handler_with_logical_coordinates(pg: Playground):
    pg.start("def miss(x, y):\n    print('canvas', x, y)\non_click(miss)\n" + LOOP)
    pg.wait_state("running")
    for lx, ly in [(-300, 200), (250, -150), (0, 0), (390, 290), (-390, -290)]:
        before = len(clicks(pg, "canvas"))
        pg.click_at(lx, ly)
        poll(lambda n=before: len(clicks(pg, "canvas")) > n, 5, f"click at {lx},{ly}")
        x, y = clicks(pg, "canvas")[-1]
        assert abs(x - lx) <= 2 and abs(y - ly) <= 2, ((lx, ly), (x, y))
    # +y is up: the upper-right click reported a positive y
    assert clicks(pg, "canvas")[0] == (clicks(pg, "canvas")[0][0], clicks(pg, "canvas")[0][1])
    assert clicks(pg, "canvas")[0][1] > 0 > clicks(pg, "canvas")[1][1]


def test_click_passes_through_a_shape_without_a_handler(pg: Playground):
    pg.start(
        "def miss(x, y):\n    print('canvas', x, y)\n"
        "Circle(0, 0, radius=100, color='gold')\n"
        "on_click(miss)\n" + LOOP
    )
    pg.wait_state("running")
    pg.click_at(0, 0)
    pg.wait_for_console("canvas")


def test_topmost_shape_wins(pg: Playground):
    pg.start(
        "Circle(0, 0, radius=100, color='gold').on_click(lambda: print('bottom'))\n"
        "Circle(0, 0, radius=50, color='red').on_click(lambda: print('top'))\n" + LOOP
    )
    pg.wait_state("running")
    pg.click_at(0, 0)
    pg.wait_for_console("top")
    pg.click_at(80, 0)
    pg.wait_for_console("bottom")
    assert pg.console() == "top\nbottom\n"


def test_handlers_may_take_fewer_arguments(pg: Playground):
    pg.start(
        "Circle(0, 0, radius=100).on_click(lambda: print('none'))\n"
        "on_click(lambda x: print('one', x))\n" + LOOP
    )
    pg.wait_state("running")
    pg.click_at(0, 0)
    pg.wait_for_console("none")
    pg.click_at(300, 0)
    pg.wait_for_console("one")


def test_a_moving_shape_can_be_clicked(pg: Playground):
    pg.start(
        "ball = Circle(-300, 0, radius=40, color='tomato')\n"
        "ball.on_click(lambda: print('caught'))\n"
        "while True:\n    ball.x = 200\n    wait(0.02)\n"
    )
    pg.wait_state("running")
    pg.settle(500)
    pg.click_at(200, 0)
    pg.wait_for_console("caught")


def test_keyboard_keys_reach_on_key(pg: Playground):
    pg.start("def pressed(key):\n    print('key', repr(key))\non_key(pressed)\n" + LOOP)
    pg.wait_state("running")
    for key, expected in [
        ("ArrowLeft", "ArrowLeft"),
        ("ArrowRight", "ArrowRight"),
        ("Space", "Space"),
        ("Enter", "Enter"),
        ("Escape", "Escape"),
        ("a", "a"),
        ("Shift+A", "A"),
        ("7", "7"),
    ]:
        pg.press(key)
        pg.wait_for_console(f"key '{expected}'")
    keys = [k for k in re.findall(r"key '(.*)'", pg.console()) if k != "Shift"]
    assert keys == ["ArrowLeft", "ArrowRight", "Space", "Enter", "Escape", "a", "A", "7"]


def test_space_is_the_word_space_not_a_blank(pg: Playground):
    pg.start("on_key(lambda key: print(repr(key)))\n" + LOOP)
    pg.wait_state("running")
    pg.press(" ")
    pg.wait_for_console("'Space'")


def test_key_combinations_with_control_are_not_forwarded(pg: Playground):
    pg.start("on_key(lambda key: print('key', key))\n" + LOOP)
    pg.wait_state("running")
    pg.press("Control+a")
    pg.press("Alt+b")
    pg.press("c")
    pg.wait_for_console("key c")
    assert pg.console() == "key c\n"


def test_holding_a_key_delivers_repeats(pg: Playground):
    pg.start("on_key(lambda key: print('key', key))\n" + LOOP)
    pg.wait_state("running")
    for _ in range(4):
        pg.page.keyboard.down("ArrowRight")
    pg.page.keyboard.up("ArrowRight")
    poll(lambda: pg.console().count("key ArrowRight") == 4, 5, "four repeats")


def test_arrow_keys_move_a_player(pg: Playground):
    pg.start(
        "player = Circle(0, 0, radius=30, color='orange')\n"
        "def pressed(key):\n"
        "    if key == 'ArrowRight':\n        player.x += 50\n"
        "    if key == 'ArrowUp':\n        player.y += 50\n"
        "on_key(pressed)\n" + LOOP
    )
    pg.wait_state("running")
    start = pg.centre(1)
    pg.press("ArrowRight")
    pg.press("ArrowUp")
    pg.settle(500)
    now = pg.centre(1)
    scale = pg.canvas_box()["width"] / 800
    assert abs((now[0] - start[0]) - 50 * scale) < 2
    assert abs((start[1] - now[1]) - 50 * scale) < 2
    pg.shot("player-moved")


def test_handlers_only_run_inside_wait(pg: Playground):
    pg.start(
        "import time\n"
        "on_click(lambda x, y: print('clicked'))\n"
        "print('ready')\n"
        "time.sleep(1.2)\n"
        "print('slept')\n"
        "wait(0.1)\n"
        "print('waited')\n"
        "wait(0.3)\n"
        "print('end')\n"
    )
    pg.wait_for_console("ready")
    pg.click_at(0, 0)
    pg.wait_for_console("end")
    lines = pg.console().split()
    assert lines == ["ready", "slept", "clicked", "waited", "end"]


def test_events_are_handled_in_arrival_order(pg: Playground):
    pg.start(
        "import time\n"
        "on_key(lambda key: print(key))\n"
        "print('ready')\n"
        "time.sleep(0.8)\n"
        "wait(0.5)\n"
        "print('end')\n"
    )
    pg.wait_for_console("ready")
    for key in "abcde":
        pg.press(key)
    pg.wait_for_console("end")
    assert pg.console().split() == ["ready", "a", "b", "c", "d", "e", "end"]


def test_events_after_the_script_finished_are_ignored(pg: Playground):
    pg.start(
        "on_click(lambda x, y: print('clicked'))\non_key(lambda key: print(key))\nprint('done')\n"
    )
    pg.wait_state("finished")
    pg.click_at(0, 0)
    pg.press("a")
    # even a hand-made request is accepted (204) and dropped
    response = pg.page.request.post(
        pg.sup.url + "event",
        data='{"t":"key","key":"b"}',
        headers={"Content-Type": "application/json"},
    )
    assert response.status == 204
    pg.page.wait_for_timeout(400)
    assert pg.console() == "done\n"
    assert pg.body().get_attribute("data-state") == "finished"


def test_events_in_a_new_run_do_not_leak_from_the_old_one(pg: Playground):
    pg.start("import time\non_key(lambda key: print('old', key))\nprint('ready')\ntime.sleep(5)\n")
    pg.wait_for_console("ready")
    pg.press("x")
    pg.edit("on_key(lambda key: print('new', key))\nprint('go')\n" + LOOP, "running")
    pg.wait_for_console("go")
    pg.press("y")
    pg.wait_for_console("new y")
    assert "old" not in pg.console() and "new x" not in pg.console()


def test_space_after_clicking_restart_still_reaches_the_program(pg: Playground):
    pg.start("on_key(lambda key: print('key', key))\n" + LOOP)
    pg.wait_state("running")
    pg.page.click("#restart")
    expect(pg.body()).to_have_attribute("data-run", "2")
    pg.wait_state("running")
    pg.press("Space")
    pg.wait_for_console("key Space")


def test_keys_do_not_scroll_or_toggle_the_console(pg: Playground):
    pg.start("on_key(lambda key: None)\n" + LOOP)
    pg.wait_state("running")
    pg.press("Space")
    pg.press("ArrowDown")
    assert pg.page.evaluate("window.scrollY") == 0
    expect(pg.page.locator("#console-panel")).to_have_attribute("data-open", "true")


def test_clicks_before_the_program_runs_are_not_sent(pg: Playground):
    pg.start("import time\ntime.sleep(0.5)\non_click(lambda x, y: print('clicked'))\n" + LOOP)
    pg.wait_state("running")
    pg.click_at(10, 10)
    pg.wait_for_console("clicked")
