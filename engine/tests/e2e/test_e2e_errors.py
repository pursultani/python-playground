"""Errors: the panel, the highlighted line, the status, dimming and recovery."""

from __future__ import annotations

import sys

from e2e_helpers import Playground
from playwright.sync_api import expect

HAS_COLUMNS = sys.version_info >= (3, 11)


def hit_line(pg: Playground) -> tuple[str, str]:
    row = pg.page.locator("#error-panel .code-line.hit")
    expect(row).to_have_count(1)
    return row.get_attribute("data-line") or "", row.locator(".src").inner_text()


def test_name_error_shows_the_line_and_underlines_the_name(pg: Playground):
    pg.start('ball = Circle()\nwait(0.1)\nbal.x = 100\nprint("never")\n')
    pg.wait_state("crashed")
    panel = pg.page.locator("#error-panel")
    expect(panel).to_be_visible()
    assert "NameError" in pg.error_text()
    assert "bal" in pg.error_text()
    assert "line 3" in pg.error_text()
    line, code = hit_line(pg)
    assert (line, code) == ("3", "bal.x = 100")
    if HAS_COLUMNS:
        mark = pg.page.locator("#error-panel .code-line.hit .mark")
        assert mark.text_content() == "bal"
    # context lines before the error are shown with line numbers
    numbers = pg.page.eval_on_selector_all(
        "#error-panel .code-line", "els => els.map(e => e.dataset.line)"
    )
    assert numbers[:3] == ["1", "2", "3"]
    expect(pg.page.locator("#status")).to_contain_text("Stopped by an error")
    # the drawing so far stays, but dimmed
    pg.expect_dimmed()
    assert pg.page.locator("#shapes > g").count() == 1
    pg.settle()
    pg.shot("name-error")
    assert "NameError" in "\n".join(pg.logs[-1:]) or any("NameError" in x for x in pg.logs)


def test_friendly_validation_message_reaches_the_student(pg: Playground):
    pg.start('Circle(x=10)\nCircle(colour="red")\n')
    pg.wait_state("crashed")
    assert "TypeError" in pg.error_text()
    assert "Circle() got an unknown property 'colour'. Did you mean 'color'?" in pg.error_text()
    assert hit_line(pg) == ("2", 'Circle(colour="red")')
    pg.settle()
    pg.shot("friendly-type-error")


def test_attribute_assignment_error_is_friendly(pg: Playground):
    pg.start('ball = Circle()\nball.x = "ten"\n')
    pg.wait_state("crashed")
    assert "x must be a number, but got 'ten'" in pg.error_text()
    assert hit_line(pg)[0] == "2"


def test_syntax_error(pg: Playground):
    pg.start('print("hello"\nCircle()\n')
    pg.wait_state("crashed")
    assert "SyntaxError" in pg.error_text()
    line, code = hit_line(pg)
    assert line in ("1", "2")
    assert "print" in pg.page.locator("#error-panel .code").inner_text()
    expect(pg.page.locator("#status")).to_contain_text("Stopped by an error")
    pg.settle()
    pg.shot("syntax-error")


def test_indentation_error(pg: Playground):
    pg.start("def go():\nprint('x')\n")
    pg.wait_state("crashed")
    assert "IndentationError" in pg.error_text()
    assert hit_line(pg)[0] == "2"


def test_error_in_a_nested_function_lists_who_called_it(pg: Playground):
    pg.start("def inner():\n    ball.x = 1\n\ndef outer():\n    inner()\n\nouter()\n")
    pg.wait_state("crashed")
    callers = pg.page.locator("#error-panel .err-callers li").all_text_contents()
    assert [c.replace("↳ ", "") for c in callers] == [
        "main.py, line 7 in <module>",
        "main.py, line 5 in outer",
    ]
    assert hit_line(pg) == ("2", "    ball.x = 1")
    assert "line 2" in pg.page.locator("#error-panel .err-where").inner_text()
    pg.settle()
    pg.shot("nested-error")


def test_error_inside_a_click_handler(pg: Playground):
    pg.start(
        "def clicked(x, y):\n    oops = missing\non_click(clicked)\nwhile True:\n    wait(0.02)\n"
    )
    pg.wait_state("running")
    pg.click_at(0, 0)
    pg.wait_state("crashed")
    assert "NameError" in pg.error_text()
    assert hit_line(pg)[0] == "2"
    callers = pg.page.locator("#error-panel .err-callers li").all_text_contents()
    assert callers and "line 5" in callers[0]
    pg.shot("handler-error")


def test_error_inside_a_key_handler(pg: Playground):
    pg.start(
        "def pressed(key):\n"
        "    if key == 'a':\n"
        "        1 / 0\n"
        "on_key(pressed)\n"
        "while True:\n"
        "    wait(0.02)\n"
    )
    pg.wait_state("running")
    pg.press("b")
    pg.press("a")
    pg.wait_state("crashed")
    assert "ZeroDivisionError" in pg.error_text()
    assert hit_line(pg) == ("3", "        1 / 0")


def test_fixing_the_file_recovers_and_undims_the_canvas(pg: Playground):
    pg.start("Circle(color='red')\nnope\n")
    pg.wait_state("crashed")
    expect(pg.page.locator("#error-panel")).to_be_visible()
    pg.edit("Circle(color='red')\nCircle(100, 0)\nwhile True:\n    wait(0.1)\n", "running")
    expect(pg.page.locator("#error-panel")).to_be_hidden()
    pg.settle(400)
    pg.expect_dimmed(False)
    assert pg.shapes().count() == 2
    expect(pg.page.locator("#status")).to_contain_text("Running")
    pg.edit("Circle(color='red')\n", "finished")
    expect(pg.page.locator("#error-panel")).to_be_hidden()


def test_a_new_error_replaces_the_old_one(pg: Playground):
    pg.start("nope1\n")
    pg.wait_state("crashed")
    assert "nope1" in pg.error_text()
    pg.edit("\n\nnope2\n", "crashed")
    assert "nope2" in pg.error_text()
    assert "nope1" not in pg.error_text()
    assert hit_line(pg)[0] == "3"


def test_error_with_a_long_message_and_unicode_line(pg: Playground):
    pg.start('name = "Zoë 🐍"\nprint(undefined_name_is_here, "héllo")\n')
    pg.wait_state("crashed")
    line, code = hit_line(pg)
    assert line == "2" and "héllo" in code
    if HAS_COLUMNS:
        assert pg.page.locator("#error-panel .code-line.hit .mark").text_content() == (
            "undefined_name_is_here"
        )


def test_tab_indented_source_is_underlined_in_the_right_place(pg: Playground):
    pg.start("def go():\n\tbad_name + 1\ngo()\n")
    pg.wait_state("crashed")
    if HAS_COLUMNS:
        assert pg.page.locator("#error-panel .code-line.hit .mark").text_content() == "bad_name"
