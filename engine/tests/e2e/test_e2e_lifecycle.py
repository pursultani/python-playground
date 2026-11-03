"""Program lifecycle, the connection to the supervisor, and reloads."""

from __future__ import annotations

import os
import signal
import time

from core.supervisor import Supervisor
from e2e_helpers import Playground, poll
from playwright.sync_api import expect

PID = "import os\nprint(os.getpid())\n"


def test_script_that_ends_is_finished_and_keeps_its_drawing(pg: Playground):
    pg.start("Circle(0, 0, color='red')\nprint('bye')\n")
    pg.wait_state("finished")
    expect(pg.page.locator("#status")).to_contain_text("Program finished")
    pg.settle(400)
    assert pg.shapes().count() == 1
    assert pg.console() == "bye\n"
    assert pg.pixel(*pg.to_screen(0, 0)) == (255, 0, 0)
    # still finished a moment later: nothing resurrects or clears it
    pg.page.wait_for_timeout(300)
    assert pg.body().get_attribute("data-state") == "finished"
    assert pg.shapes().count() == 1
    pg.shot("finished")
    assert "Program finished" in pg.logs


def test_running_status_while_waiting(pg: Playground):
    pg.start("Circle()\nwhile True:\n    wait(0.1)\n")
    pg.wait_state("running")
    expect(pg.page.locator("#status")).to_contain_text("Running")
    pg.shot("running")


def test_exit_function_finishes(pg: Playground):
    pg.start("Circle()\nprint('before')\nexit()\nprint('after')\n")
    pg.wait_state("finished")
    assert pg.console() == "before\n"
    assert pg.shapes().count() == 1


def test_sys_exit_finishes(pg: Playground):
    pg.start("import sys\nprint('before')\nsys.exit(3)\n")
    pg.wait_state("finished")
    assert pg.console() == "before\n"


def test_infinite_loop_without_wait_is_killed_on_edit(pg: Playground):
    pg.start(PID + "Circle(color='green')\nwhile True:\n    pass\n")
    pid = pg.pid()
    pg.wait_state("running")
    # the drawing still reaches the page even though the program never calls wait()
    expect(pg.shapes()).to_have_count(1)
    started = time.monotonic()
    pg.edit("print('recovered')\n", "finished")
    assert time.monotonic() - started < 4
    pg.wait_for_console("recovered")
    poll(lambda: not _alive(pid), 5, "the old child to be gone")


def test_infinite_loop_stuck_in_sleep_is_killed_on_restart_button(pg: Playground):
    pg.start(PID + "import time\ntime.sleep(1000)\n")
    pid = pg.pid()
    pg.page.click("#restart")
    expect(pg.body()).to_have_attribute("data-run", "2")
    poll(lambda: not _alive(pid), 5, "the old child to be gone")


def test_child_killed_from_outside_is_crashed(pg: Playground):
    pg.start(PID + "Circle()\nwhile True:\n    wait(0.1)\n")
    pid = pg.pid()
    pg.wait_state("running")
    os.kill(pid, signal.SIGKILL)
    pg.wait_state("crashed")
    assert "The program stopped unexpectedly" in pg.error_text()
    expect(pg.page.locator("#status")).to_contain_text("Stopped by an error")
    # the drawing stays, and a save recovers
    assert pg.shapes().count() == 1
    pg.edit("print('back')\n", "finished")
    expect(pg.page.locator("#error-panel")).to_be_hidden()


def test_reload_shows_the_current_state_from_the_snapshot(pg: Playground):
    pg.start(
        "canvas('lightblue')\nCircle(100, 50, color='red', title='me')\n"
        "print('hello')\nwhile True:\n    wait(0.1)\n"
    )
    pg.wait_for_console("hello")
    pg.page.reload()
    pg.page.wait_for_selector("body[data-conn='ok']")
    pg.wait_state("running")
    pg.wait_for_console("hello")
    assert pg.ids() == [1]
    assert pg.page.locator("#background").get_attribute("fill") == "lightblue"
    assert pg.shape(1).locator("text.title").text_content() == "me"
    assert pg.console() == "hello\n"
    expect(pg.page.locator("#script-name")).to_have_text("main.py")


def test_reload_after_a_crash_shows_the_error_again(pg: Playground):
    pg.start("Circle()\nboom\n")
    pg.wait_state("crashed")
    pg.page.reload()
    pg.wait_state("crashed")
    assert "boom" in pg.error_text()
    assert pg.shapes().count() == 1
    pg.expect_dimmed()


def test_two_browser_tabs_stay_in_sync(pg: Playground):
    pg.start("print('x')\nwhile True:\n    wait(0.05)\n")
    first = pg.page
    pg.wait_for_console("x")
    second = pg.new_page()
    second.goto(pg.sup.url)
    expect(second.locator("#console")).to_contain_text("x")
    pg.edit("print('y')\nCircle()\nwhile True:\n    wait(0.05)\n", "running")
    expect(first.locator("#console")).to_have_text("y\n")
    expect(second.locator("#console")).to_have_text("y\n")
    expect(second.locator("#shapes > g")).to_have_count(1)


def test_supervisor_restart_shows_the_banner_then_recovers(pg: Playground):
    pg.start(
        "canvas('lightyellow')\nCircle(0, 0, color='red')\nprint('hi')\n"
        "while True:\n    wait(0.1)\n"
    )
    pg.wait_for_console("hi")
    port = pg.sup.port
    pg.sup.stop()
    expect(pg.page.locator("#banner")).to_be_visible()
    expect(pg.body()).to_have_attribute("data-conn", "lost")
    assert "Disconnected" in pg.page.locator("#banner").inner_text()
    pg.shot("banner")
    # a new supervisor (a student pressing Ctrl+C and running again) on the same port
    pg.supervisor = Supervisor(pg.script, port=port, poll_interval=0.05)
    pg.supervisor.start()
    expect(pg.page.locator("#banner")).to_be_hidden(timeout=15000)
    pg.wait_state("running")
    pg.wait_for_console("hi")
    assert pg.console() == "hi\n"
    assert pg.shapes().count() == 1
    # and live refresh still works over the new connection
    pg.edit("print('after')\nwhile True:\n    wait(0.1)\n", "running")
    pg.wait_for_console("after")


def test_reconnect_is_fast_thanks_to_the_retry_hint(pg: Playground):
    pg.start("print('hi')\nwhile True:\n    wait(0.1)\n")
    pg.wait_for_console("hi")
    port = pg.sup.port
    pg.sup.stop()
    expect(pg.body()).to_have_attribute("data-conn", "lost")
    pg.supervisor = Supervisor(pg.script, port=port, poll_interval=0.05)
    pg.supervisor.start()
    started = time.monotonic()
    expect(pg.body()).to_have_attribute("data-conn", "ok", timeout=5000)
    assert time.monotonic() - started < 3


def test_unchanged_page_script_is_served_without_caching(pg: Playground):
    pg.start("pass\n")
    response = pg.page.request.get(pg.sup.url + "static/app.js")
    assert response.headers["cache-control"] == "no-store"
    assert "javascript" in response.headers["content-type"]


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True
