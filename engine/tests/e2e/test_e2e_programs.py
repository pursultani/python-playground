"""Realistic student programs, window sizes and odd-but-plausible situations."""

from __future__ import annotations

import re

from e2e_helpers import Playground, poll
from playwright.sync_api import expect

LOOP = "while True:\n    wait(0.02)\n"


def test_a_subclass_with_methods_and_attributes(pg: Playground):
    pg.start(
        "class Player(Circle):\n"
        "    def __init__(self):\n"
        "        super().__init__(x=0, y=-200, color='orange', name='player')\n"
        "        self.speed = 40\n"
        "    def move_left(self):\n"
        "        self.x -= self.speed\n"
        "player = Player()\n"
        "on_key(lambda key: player.move_left() if key == 'ArrowLeft' else None)\n"
        "print(player)\n" + LOOP
    )
    pg.wait_for_console("Player(")
    assert pg.console().startswith("Player(")
    before = pg.centre(1)[0]
    pg.press("ArrowLeft")
    pg.settle(400)
    scale = pg.canvas_box()["width"] / 800
    assert abs((before - pg.centre(1)[0]) - 40 * scale) < 2


def test_error_in_a_subclass_constructor_points_at_the_students_line(pg: Playground):
    pg.start(
        "class Ball(Circle):\n"
        "    def __init__(self):\n"
        "        super().__init__(colour='red')\n"
        "Ball()\n"
    )
    pg.wait_state("crashed")
    assert "Did you mean 'color'?" in pg.error_text()
    assert pg.page.locator("#error-panel .code-line.hit").get_attribute("data-line") == "3"
    callers = pg.page.locator("#error-panel .err-callers li").all_text_contents()
    assert any("line 4" in c for c in callers)


def test_error_in_an_imported_module_names_that_file(pg: Playground):
    (pg.directory / "helper.py").write_text("def go():\n    return missing_thing\n")
    pg.start("import helper\nhelper.go()\n")
    pg.wait_state("crashed")
    assert "helper.py, line 2" in pg.error_text()
    assert pg.page.locator("#error-panel .code-line.hit .src").inner_text().strip() == (
        "return missing_thing"
    )


def test_input_gives_a_readable_error_instead_of_hanging(pg: Playground):
    pg.start("name = input('name? ')\nprint(name)\n")
    pg.wait_state("crashed")
    assert "EOFError" in pg.error_text()


def test_script_with_crlf_line_endings_and_a_bom(pg: Playground):
    pg.start(b"\xef\xbb\xbfCircle(color='red')\r\nprint('crlf ok')\r\nboom\r\n")
    pg.wait_state("crashed")
    pg.wait_for_console("crlf ok")
    assert pg.page.locator("#error-panel .code-line.hit").get_attribute("data-line") == "3"


def test_directory_with_spaces_and_unicode(chromium, tmp_path):
    folder = tmp_path / "my project é 🐍"
    folder.mkdir()
    pg = Playground(folder, chromium, "unicode-dir")
    try:
        pg.start("print('hello from a funny folder')\nCircle()\n")
        pg.wait_state("finished")
        pg.wait_for_console("funny folder")
    finally:
        pg.close()


def test_clicks_map_correctly_at_other_window_sizes_and_with_the_console_closed(pg: Playground):
    pg.start(
        "on_click(lambda x, y: print('at', x, y))\n" + LOOP, viewport={"width": 700, "height": 560}
    )
    pg.wait_state("running")
    seen = 0
    for size in [(700, 560), (1400, 700), (500, 900), (1000, 500)]:
        pg.page.set_viewport_size({"width": size[0], "height": size[1]})
        for point in [(-300, 200), (350, -250), (0, 0)]:
            pg.click_at(*point)
            seen += 1
            poll(lambda n=seen: len(re.findall(r"at -?\d+ -?\d+", pg.console())) >= n, 5, "click")
            x, y = [int(v) for v in re.findall(r"at (-?\d+) (-?\d+)", pg.console())[-1]]
            tolerance = 800 / pg.canvas_box()["width"] + 1.5
            assert abs(x - point[0]) <= tolerance and abs(y - point[1]) <= tolerance, (
                size,
                point,
                x,
                y,
            )
    pg.page.click("#console-toggle")
    pg.click_at(123, -45)
    poll(lambda: "at 12" in pg.console().split("\n")[-2] or "at 12" in pg.console(), 5, "click")
    pg.shot("small-window")


def test_clicks_in_the_letterbox_outside_the_canvas_are_ignored(pg: Playground):
    pg.start(
        "on_click(lambda x, y: print('at', x, y))\n" + LOOP, viewport={"width": 1400, "height": 500}
    )
    pg.wait_state("running")
    box = pg.canvas_box()
    pg.page.mouse.click(box["x"] - 10, box["y"] + 100)
    pg.page.mouse.click(box["x"] + box["width"] + 10, box["y"] + 100)
    pg.click_at(0, 0)
    pg.wait_for_console("at")
    assert len(re.findall(r"at -?\d+", pg.console())) == 1


def test_resizing_the_window_keeps_the_picture_in_proportion(pg: Playground):
    pg.start("Circle(100, 100, radius=50, color='red')\nRectangle(-200, -100)\n")
    pg.wait_state("finished")
    for size in [(600, 700), (1300, 800), (900, 450)]:
        pg.page.set_viewport_size({"width": size[0], "height": size[1]})
        pg.page.wait_for_timeout(100)
        box = pg.canvas_box()
        assert abs(box["width"] / box["height"] - 4 / 3) < 0.01
        cx, cy = pg.centre(1)
        sx, sy = pg.to_screen(100, 100)
        assert abs(cx - sx) < 1.5 and abs(cy - sy) < 1.5
        wrap = pg.page.locator("#canvas").bounding_box()
        assert wrap is not None and wrap["width"] <= size[0]


def test_a_catch_the_stars_style_game_loop(pg: Playground):
    pg.start(
        "import random\n"
        "random.seed(3)\n"
        "score = 0\n"
        "label = Text('Score: 0', 0, 260, size=28)\n"
        "stars = []\n"
        "def spawn():\n"
        "    s = Text('⭐', random.randint(-300, 300), 300, size=40)\n"
        "    stars.append(s)\n"
        "def clicked(x, y):\n"
        "    global score\n"
        "    for s in list(stars):\n"
        "        if abs(s.x - x) < 30 and abs(s.y - y) < 30:\n"
        "            s.remove(); stars.remove(s); score += 1\n"
        "            label.text = f'Score: {score}'\n"
        "on_click(clicked)\n"
        "tick = 0\n"
        "while True:\n"
        "    tick += 1\n"
        "    if tick % 10 == 0:\n"
        "        spawn()\n"
        "    for s in list(stars):\n"
        "        s.y -= 6\n"
        "        if s.y < -330:\n"
        "            s.remove(); stars.remove(s)\n"
        "    wait(0.03)\n"
    )
    pg.wait_state("running")
    expect(pg.page.locator("g[data-type='text']")).not_to_have_count(1, timeout=8000)
    pg.page.wait_for_timeout(600)
    stars = pg.page.locator("g[data-type='text']")
    assert stars.count() >= 2
    # click directly on the lowest star
    positions = pg.page.eval_on_selector_all(
        "g[data-type='text']",
        "els => els.map(e => { const b = e.getBoundingClientRect();"
        " return [e.dataset.id, b.x + b.width / 2, b.y + b.height / 2]; })",
    )
    positions = [p for p in positions if p[0] != "1"]
    positions.sort(key=lambda p: -p[2])
    _, px, py = positions[0]
    # the star keeps falling 6 units per 30 ms: aim a little ahead of it
    pg.page.mouse.click(px, py + 8)
    expect(pg.page.locator("g[data-id='1'] text.content")).to_have_text("Score: 1", timeout=5000)
    pg.shot("stars")
