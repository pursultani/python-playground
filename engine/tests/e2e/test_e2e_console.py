"""print output, stderr, clearing and the console toggle."""

from __future__ import annotations

from e2e_helpers import Playground
from playwright.sync_api import expect


def test_print_output_appears_in_the_console(pg: Playground):
    pg.start('print("Hello!")\nprint("a", "b", 3)\nprint("no newline", end="")\n')
    pg.wait_state("finished")
    assert pg.console() == "Hello!\na b 3\nno newline"
    expect(pg.page.locator("#console-count")).to_have_text("3")
    pg.shot("console")


def test_stderr_is_styled_differently(pg: Playground):
    pg.start('import sys\nprint("fine")\nprint("uh oh", file=sys.stderr)\nprint("fine again")\n')
    pg.wait_state("finished")
    assert pg.console() == "fine\nuh oh\nfine again\n"
    classes = pg.page.eval_on_selector_all("#console > span", "els => els.map(e => e.className)")
    assert classes == ["stdout", "stderr", "stdout"]
    err_color = pg.page.locator("#console > span.stderr").evaluate("e => getComputedStyle(e).color")
    out_color = pg.page.locator("#console > span.stdout").first.evaluate(
        "e => getComputedStyle(e).color"
    )
    assert err_color != out_color
    pg.shot("stderr")


def test_unicode_and_blank_lines_survive_the_round_trip(pg: Playground):
    pg.start('print("héllo 🌍 \\u4f60\\u597d")\nprint()\nprint("end")\n')
    pg.wait_state("finished")
    assert pg.console() == "héllo 🌍 你好\n\nend\n"


def test_console_clears_on_rerun(pg: Playground):
    pg.start('print("first run")\n')
    pg.wait_state("finished")
    assert "first run" in pg.console()
    pg.edit('print("second run")\n', expect_state="finished")
    assert pg.console() == "second run\n"


def test_console_toggle_and_clear_button(pg: Playground):
    pg.start('print("one")\nprint("two")\nwhile True:\n    wait(0.1)\n')
    pg.wait_for_console("two")
    panel = pg.page.locator("#console-panel")
    expect(panel).to_have_attribute("data-open", "true")
    expect(pg.page.locator("#console")).to_be_visible()
    pg.page.click("#console-toggle")
    expect(panel).to_have_attribute("data-open", "false")
    expect(pg.page.locator("#console")).to_be_hidden()
    pg.shot("console-closed")
    # the choice is remembered when the page is reloaded
    pg.page.reload()
    pg.page.wait_for_selector("body[data-conn='ok']")
    expect(pg.page.locator("#console-panel")).to_have_attribute("data-open", "false")
    pg.page.click("#console-toggle")
    expect(pg.page.locator("#console")).to_be_visible()
    pg.wait_for_console("two")
    pg.page.click("#console-clear")
    assert pg.console() == ""


def test_output_printed_before_an_error_is_kept_and_error_goes_to_the_panel(pg: Playground):
    pg.start('print("before")\nprint(nope)\n')
    pg.wait_state("crashed")
    assert pg.console() == "before\n"
    expect(pg.page.locator("#error-panel")).to_contain_text("NameError")


def test_print_inside_a_click_handler(pg: Playground):
    pg.start(
        "def clicked(x, y):\n    print('clicked at', x, y)\n"
        "on_click(clicked)\nwhile True:\n    wait(0.02)\n"
    )
    pg.wait_state("running")
    pg.click_at(0, 0)
    pg.wait_for_console("clicked at")
