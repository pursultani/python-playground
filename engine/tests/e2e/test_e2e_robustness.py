"""Things that go wrong in classrooms: restart spam, orphan processes, live guide changes."""

from __future__ import annotations

import os
import subprocess

from e2e_helpers import Playground, poll
from playwright.sync_api import expect

PID_LOOP = "import os\nprint(os.getpid())\nwhile True:\n    wait(0.05)\n"


def children_running(pg: Playground) -> list[int]:
    if os.path.isdir("/proc/self"):
        pids = []
        for entry in os.listdir("/proc"):
            if not entry.isdigit() or int(entry) == os.getpid():
                continue
            try:
                with open(f"/proc/{entry}/cmdline", "rb") as cmdline:
                    text = cmdline.read().replace(b"\0", b" ").decode(errors="replace")
            except OSError:
                continue
            if "core.runner" in text and text.rstrip().endswith(str(pg.script)):
                pids.append(int(entry))
        return pids
    result = subprocess.run(
        ["pgrep", "-f", f"core.runner.* {pg.script}"], capture_output=True, text=True
    )
    return [int(line) for line in result.stdout.split()]


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def test_restart_spam_leaves_exactly_one_child(pg: Playground):
    pg.start(PID_LOOP)
    pids = [pg.pid()]
    for run in range(2, 7):
        pg.page.click("#restart")
        expect(pg.body()).to_have_attribute("data-run", str(run))
    pg.wait_state("running")
    final = pg.pid()
    pids.append(final)
    poll(lambda: sum(alive(p) for p in set(pids)) == 1, 5, "only the newest child to survive")
    assert alive(final)
    poll(lambda: len(children_running(pg)) == 1, 5, "exactly one runner process for this script")


def test_stopping_the_supervisor_kills_the_child(pg: Playground):
    pg.start(PID_LOOP)
    pid = pg.pid()
    pg.sup.stop()
    poll(lambda: not alive(pid), 5, "the child to exit")


def test_new_shapes_appear_in_place_instead_of_flying_in(pg: Playground):
    pg.start("wait(0.3)\nCircle(300, 200, radius=20, color='red')\nwhile True:\n    wait(0.1)\n")
    pg.wait_state("running")
    pg.page.wait_for_selector("#shapes > g")
    # the very first painted position is already the final one
    first = pg.page.evaluate(
        "() => { const e = document.querySelector('#shapes > g');"
        " return getComputedStyle(e).transform; }"
    )
    assert first == pg.transform(1)
    assert first.startswith("matrix(") and "300" in first and "-200" in first


def test_guides_update_live(pg: Playground):
    pg.start(
        "grid = Grid()\n"
        "axis = Axis()\n"
        "wait(0.3)\n"
        "grid.color = 'red'\n"
        "grid.style = 'dotted'\n"
        "axis.labels = False\n"
        "axis.size = 100\n"
        "axis.width = 6\n"
        "print('changed')\n"
        "while True:\n    wait(0.1)\n"
    )
    pg.wait_for_console("changed")
    pg.settle()
    grid_path = pg.page.locator("g[data-type='grid'] path")
    assert grid_path.get_attribute("stroke") == "red"
    assert grid_path.get_attribute("stroke-dasharray") == "1 5"
    assert pg.page.locator("g[data-type='axis'] text").count() == 0
    assert pg.page.locator("g[data-type='axis'] path").first.get_attribute("stroke-width") == "6"
    pg.shot("guides-changed")


def test_line_follows_property_changes(pg: Playground):
    pg.start(
        "line = Line(-100, 0, 100, 0, width=8, color='green')\n"
        "wait(0.2)\n"
        "line.x2 = 100\n"
        "line.y2 = 100\n"
        "line.x = -100\n"
        "line.y = -100\n"
        "print('moved')\n"
        "while True:\n    wait(0.1)\n"
    )
    pg.wait_for_console("moved")
    pg.settle()
    # now it runs from (-100,-100) to (100,100): its middle is the canvas centre
    sx, sy = pg.to_screen(0, 0)
    assert pg.pixel(sx, sy) == (0, 128, 0)
    px, py = pg.to_screen(50, 50)
    assert pg.pixel(px, py) == (0, 128, 0)
    ox, oy = pg.to_screen(50, -50)
    assert pg.pixel(ox, oy) != (0, 128, 0)


def test_text_and_title_change_live(pg: Playground):
    pg.start(
        "t = Text('one', 0, 100)\n"
        "c = Circle(0, -100, title='a')\n"
        "wait(0.2)\n"
        "t.text = 'two'\n"
        "t.size = 60\n"
        "c.title = ''\n"
        "print('changed')\n"
        "while True:\n    wait(0.1)\n"
    )
    pg.wait_for_console("changed")
    expect(pg.page.locator("g[data-type='text'] text.content")).to_have_text("two")
    assert pg.page.locator("g[data-type='text'] text.content").get_attribute("font-size") == "60"
    expect(pg.page.locator("g[data-type='circle'] text.title")).to_be_hidden()


def test_rotation_direction_is_counter_clockwise(pg: Playground):
    pg.start(
        "Rectangle(0, 0, width=200, height=20, color='black', rotation=90).on_click(lambda: None)\n"
        "Rectangle(0, 200, width=200, height=20, color='red', rotation=45)\n"
    )
    pg.wait_state("finished")
    pg.settle()
    # rotation=90 turns the wide bar into a tall one
    bar = pg.shape(1).bounding_box()
    assert bar is not None and bar["height"] > bar["width"] * 5
    # +45 degrees counter-clockwise: the right end of the bar goes UP on screen
    # so the pixel up-right of the centre is red, and the pixel down-right is not
    up_right = pg.to_screen(60, 200 + 60)
    down_right = pg.to_screen(60, 200 - 60)
    assert pg.pixel(*up_right) == (255, 0, 0)
    assert pg.pixel(*down_right) != (255, 0, 0)


def test_many_quick_edits_never_leave_stale_error_or_console_text(pg: Playground):
    pg.start("print('v0')\nwhile True:\n    wait(0.05)\n")
    pg.wait_for_console("v0")
    for i in range(1, 8):
        source = (
            f"print('v{i}')\nbad{i}\n" if i % 2 else f"print('v{i}')\nwhile True:\n    wait(0.05)\n"
        )
        pg.script.write_text(source)
        pg.page.wait_for_timeout(120)
    pg.wait_for_console("v7")
    pg.wait_state("crashed")
    assert pg.console() == "v7\n"
    assert "bad7" in pg.error_text()


def test_atomic_save_like_vim_or_vscode_restarts_once_with_the_new_code(pg: Playground):
    pg.start("print('old')\nwhile True:\n    wait(0.05)\n")
    pg.wait_for_console("old")
    temp = pg.directory / ".main.py.swp-123"
    temp.write_text("print('new')\nwhile True:\n    wait(0.05)\n")
    os.replace(temp, pg.script)
    pg.wait_for_console("new")
    pg.wait_state("running")
    assert pg.console() == "new\n"
    assert pg.sup.run == 2


def test_delete_then_recreate_quickly_ends_on_the_new_code(pg: Playground):
    pg.start("print('old')\nwhile True:\n    wait(0.05)\n")
    pg.wait_for_console("old")
    pg.script.unlink()
    pg.script.write_text("print('recreated')\nwhile True:\n    wait(0.05)\n")
    pg.wait_for_console("recreated")
    pg.wait_state("running")
    pg.page.wait_for_timeout(400)
    assert pg.console() == "recreated\n"


def test_empty_script_finishes_cleanly(pg: Playground):
    pg.start("")
    pg.wait_state("finished")
    assert pg.shapes().count() == 0
    pg.edit("\n\n   \n", "finished")
    pg.edit("# only a comment", "finished")


def test_underline_is_right_after_emoji_on_the_same_line(pg: Playground):
    pg.start("s = '🐍🐍'; t = oops_name\n")
    pg.wait_state("crashed")
    import sys

    if sys.version_info >= (3, 11):
        assert pg.page.locator("#error-panel .mark").text_content() == "oops_name"


def test_a_very_long_line_and_message_stay_inside_the_panel(pg: Playground):
    long_name = "x" * 200
    pg.start(f"value = 1\nprint(value + {long_name})\n")
    pg.wait_state("crashed")
    pg.settle()
    panel = pg.page.locator("#error-panel").bounding_box()
    assert panel is not None
    assert panel["x"] >= 0 and panel["x"] + panel["width"] <= 1100
    overflow = pg.page.evaluate(
        "() => { const p = document.getElementById('error-panel');"
        " return p.scrollWidth - p.clientWidth; }"
    )
    assert overflow <= 1
    pg.shot("long-line")


def test_syntax_error_in_an_imported_module(pg: Playground):
    (pg.directory / "helper.py").write_text("def broken(:\n    pass\n")
    pg.start("import helper\n")
    pg.wait_state("crashed")
    assert "SyntaxError" in pg.error_text()
    assert "helper.py" in pg.error_text()


def test_files_named_like_python_modules_warn_but_do_not_break_the_run(pg: Playground):
    (pg.directory / "queue.py").write_text("raise RuntimeError('the wrong queue')\n")
    (pg.directory / "json.py").write_text("raise RuntimeError('the wrong json')\n")
    pg.start("import json, queue\nCircle()\nprint('still works')\n")
    pg.wait_state("finished")
    console = pg.console()
    assert "queue.py has the same name as a Python module that comes with Python" in console
    assert "Rename it, for example my_queue.py." in console
    assert "json.py has the same name" in console
    assert console.endswith("still works\n")
    assert pg.page.eval_on_selector_all("#console > span.stderr", "els => els.length") >= 1


def test_a_script_named_random_runs_and_is_warned_about(pg: Playground):
    pg.script = pg.directory / "random.py"
    pg.start("import random\nCircle()\nprint(random.randint(1, 1))\n")
    pg.wait_state("finished")
    assert "random.py has the same name as a Python module" in pg.console()
    assert pg.console().endswith("1\n")


def test_input_explains_that_it_does_not_work(pg: Playground):
    pg.start("name = input('Your name? ')\n")
    pg.wait_state("crashed")
    assert "input() does not work in Python Playground" in pg.error_text()
    assert "on_click or on_key" in pg.error_text()


def test_a_file_that_is_not_utf8_gets_a_friendly_error(pg: Playground):
    pg.start("print('héllo')\n".encode("latin-1"))
    pg.wait_state("crashed")
    text = pg.error_text()
    assert "main.py isn't saved as UTF-8. Save the file again as UTF-8." in text
    assert str(pg.directory) not in text
