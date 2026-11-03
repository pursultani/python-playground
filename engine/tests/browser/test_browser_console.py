"""Console panel and error panel."""

from __future__ import annotations

from collections.abc import Callable

from page_driver import App, create, error, frame, print_, run
from playwright.sync_api import expect


def test_console_shows_stdout_and_stderr(app: App) -> None:
    app.send(print_("Hello"), print_("!\n"), print_("Oops\n", "stderr"), print_("last\n"))
    app.sync()
    assert app.console_text() == "Hello!\nOops\nlast\n"
    expect(app.page.locator("#console .stdout").first).to_have_text("Hello!\n")
    expect(app.page.locator("#console .stderr")).to_have_text("Oops\n")
    color = app.page.locator("#console .stderr").evaluate("e => getComputedStyle(e).color")
    assert color != app.page.locator("#console .stdout").first.evaluate(
        "e => getComputedStyle(e).color"
    )
    ws = app.page.locator("#console").evaluate("e => getComputedStyle(e).whiteSpace")
    assert ws == "pre-wrap"


def test_console_line_count(app: App) -> None:
    expect(app.page.locator("#console-count")).to_be_hidden()
    app.send(print_("a\nb\n"), print_("c"))
    expect(app.page.locator("#console-count")).to_have_text("3")
    app.send(print_("\n"))
    expect(app.page.locator("#console-count")).to_have_text("3")


def test_console_is_cleared_on_new_run_and_by_button(app: App) -> None:
    app.send(print_("one\n"))
    app.sync()
    app.page.click("#console-clear")
    assert app.console_text() == ""
    app.send(print_("two\n"), run(2))
    app.sync()
    assert app.console_text() == ""


def test_console_is_capped_at_2000_chunks(app: App) -> None:
    app.send(*[print_(f"line {i}\n") for i in range(2500)])
    app.sync()
    chunks = app.page.locator("#console > span")
    expect(chunks).to_have_count(2000)
    text = app.console_text()
    assert text.startswith("line 500\n")
    assert text.endswith("line 2499\n")
    expect(app.page.locator("#console-count")).to_have_text("2000")


def test_console_autoscrolls_unless_user_scrolled_up(app: App) -> None:
    app.send(*[print_(f"line {i}\n") for i in range(200)])
    app.sync()
    assert (
        app.page.evaluate(
            "(() => { const c = document.getElementById('console'); "
            "return c.scrollHeight - c.scrollTop - c.clientHeight; })()"
        )
        < 2
    )
    app.page.evaluate("document.getElementById('console').scrollTop = 0")
    app.send(*[print_(f"more {i}\n") for i in range(50)])
    app.sync()
    assert app.page.evaluate("document.getElementById('console').scrollTop") == 0


def test_console_toggle_is_persisted(app: App) -> None:
    app.send(print_("hi\n"))
    app.sync()
    expect(app.page.locator("#console")).to_be_visible()
    app.page.click("#console-toggle")
    expect(app.page.locator("#console")).to_be_hidden()
    app.page.reload()
    app.page.wait_for_selector("body[data-conn='ok']")
    expect(app.page.locator("#console")).to_be_hidden()
    app.page.click("#console-toggle")
    app.page.reload()
    app.page.wait_for_selector("body[data-conn='ok']")
    expect(app.page.locator("#console")).to_be_visible()


def test_console_open_by_default(app: App) -> None:
    expect(app.page.locator("#console-panel")).to_have_attribute("data-open", "true")
    expect(app.page.locator("#console")).to_be_visible()


FRAMES = [
    {"file": "main.py", "line": 20, "function": "<module>", "code": "a()", "col": 1, "end_col": 4},
    {"file": "main.py", "line": 12, "function": "a", "code": "b()", "col": 5, "end_col": 8},
    {"file": "util.py", "line": 7, "function": "b", "code": "c()"},
    {"file": "main.py", "line": 3, "function": "c", "code": "d()"},
    {"file": "main.py", "line": 2, "function": "d", "code": "e()"},
    {
        "file": "main.py",
        "line": 8,
        "function": "e",
        "code": "    bal.x += 1",
        "col": 5,
        "end_col": 8,
    },
]
CONTEXT = [
    {"line": 6, "code": "def go():"},
    {"line": 7, "code": "    ball = Circle()"},
    {"line": 8, "code": "    bal.x += 1"},
    {"line": 9, "code": "    print(ball)"},
]


def test_error_panel_content(app: App) -> None:
    app.send(
        error(
            "NameError",
            "name 'bal' is not defined",
            frames=FRAMES[:2] + FRAMES[-1:],
            context=CONTEXT,
        )
    )
    panel = app.page.locator("#error-panel")
    expect(panel).to_be_visible()
    expect(panel.locator(".err-title")).to_contain_text("NameError")
    expect(panel.locator(".err-message")).to_have_text("name 'bal' is not defined")
    expect(panel.locator(".err-where")).to_have_text("File main.py, line 8")
    callers = panel.locator(".err-callers li")
    assert callers.all_text_contents() == [
        "main.py, line 20 in <module>",
        "main.py, line 12 in a",
    ]
    rows = panel.locator(".code-line")
    expect(rows).to_have_count(4)
    hit = panel.locator(".code-line.hit")
    expect(hit).to_have_count(1)
    expect(hit.locator(".no")).to_have_text("8")
    expect(hit.locator(".mark")).to_have_text("bal")
    assert hit.locator(".src").text_content() == "    bal.x += 1"
    expect(app.page.locator("body")).to_have_class("has-error")


def test_error_column_span_uses_characters_not_bytes(app: App) -> None:
    app.send(
        error(
            "NameError",
            "x",
            frames=[
                {
                    "file": "main.py",
                    "line": 1,
                    "function": "<module>",
                    "code": "é🌍 = bal",
                    "col": 6,
                    "end_col": 9,
                }
            ],
            context=[{"line": 1, "code": "é🌍 = bal"}],
        )
    )
    expect(app.page.locator(".code-line.hit .mark")).to_have_text("bal")


def test_error_without_columns_highlights_the_line_only(app: App) -> None:
    app.send(
        error(
            "TypeError",
            "x",
            frames=[{"file": "main.py", "line": 8, "function": "<module>", "code": "a"}],
            context=CONTEXT,
        )
    )
    expect(app.page.locator(".code-line.hit")).to_have_count(1)
    expect(app.page.locator(".code-line .mark")).to_have_count(0)


def test_error_panel_limits_callers(app: App) -> None:
    many = [{"file": "main.py", "line": n, "function": f"f{n}", "code": "x()"} for n in range(1, 9)]
    app.send(error("RecursionError", "deep", frames=many, context=[]))
    items = app.page.locator(".err-callers li").all_text_contents()
    assert items[:4] == [f"main.py, line {n} in f{n}" for n in range(1, 5)]
    assert items[4] == "…"
    assert len(items) == 5


def test_error_panel_without_frames_still_shows_message(app: App) -> None:
    app.send(error("RuntimeError", "The program stopped unexpectedly"))
    expect(app.page.locator(".err-message")).to_have_text("The program stopped unexpectedly")
    expect(app.page.locator(".code")).to_have_count(0)


def test_error_panel_dims_canvas_and_clears_on_run(app: App) -> None:
    app.send(frame(create(1, "circle")), error("ValueError", "x"))
    expect(app.page.locator("#error-panel")).to_be_visible()
    app.page.wait_for_function(
        "getComputedStyle(document.getElementById('canvas-wrap')).opacity < 0.5"
    )
    app.send(run(2))
    expect(app.page.locator("#error-panel")).to_be_hidden()
    app.page.wait_for_function(
        "getComputedStyle(document.getElementById('canvas-wrap')).opacity === '1'"
    )


def test_error_panel_is_hidden_after_snapshot_without_error(open_app: Callable[..., App]) -> None:
    app = open_app()
    app.send(error("ValueError", "x"))
    expect(app.page.locator("#error-panel")).to_be_visible()
    app.send({**app.host.snapshot, "error": None})
    expect(app.page.locator("#error-panel")).to_be_hidden()
