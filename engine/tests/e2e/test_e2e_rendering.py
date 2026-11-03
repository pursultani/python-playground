"""Drawing: every shape, motion, guides, background and the coordinate system."""

from __future__ import annotations

from e2e_helpers import Playground
from playwright.sync_api import expect

ALL_SHAPES = """
canvas("ivory")
Grid()
Axis()
Circle(-250, 150, radius=60, color="tomato", title="circle")
Rectangle(0, 150, width=140, height=80, color="gold", title="rect")
Triangle(250, 150, width=120, height=110, color="seagreen", title="tri")
Line(-300, -50, -100, -150, width=8, color="purple", title="line")
Text("Hello 🐍", 100, -100, size=48, color="navy")
Circle(250, -150, radius=40, color="orange", rotation=30, opacity=0.5)
Rectangle(-250, -200, width=100, height=40, color="crimson", rotation=45, title="turned")
"""


def test_every_shape_type_renders(pg: Playground):
    pg.start(ALL_SHAPES)
    pg.wait_state("finished")
    types = pg.page.eval_on_selector_all("#shapes > g", "els => els.map(e => e.dataset.type)")
    assert types == ["circle", "rectangle", "triangle", "line", "text", "circle", "rectangle"]
    guides = pg.page.eval_on_selector_all("#guides > g", "els => els.map(e => e.dataset.type)")
    assert guides == ["grid", "axis"]
    # ids are creation order: Grid=1, Axis=2, then the shapes
    assert pg.page.locator("g[data-type='text'] text.content").text_content() == "Hello 🐍"
    for type_, title in (("circle", "circle"), ("rectangle", "rect"), ("triangle", "tri")):
        title_el = pg.page.locator(f"g[data-type='{type_}'] text.title").first
        expect(title_el).to_be_visible()
        assert title_el.text_content() == title
    expect(pg.page.locator("g[data-type='line'] text.title")).to_have_text("line")
    opacities = pg.page.eval_on_selector_all(
        "#shapes > g", "els => els.map(e => getComputedStyle(e).opacity)"
    )
    assert opacities[5] == "0.5"
    pg.settle()
    pg.shot("all-shapes")
    order = pg.page.evaluate("[...document.querySelectorAll('#canvas > *')].map(e => e.id)")
    assert order == ["background", "guides", "shapes"]


def test_properties_changed_in_a_loop_animate(pg: Playground):
    pg.start(
        """
ball = Circle(-300, 0, color="tomato")
box = Rectangle(0, 100, width=40, height=40, color="gold")
for step in range(60):
    ball.x += 10
    box.rotation += 6
    wait(0.05)
print("done")
"""
    )
    seen_x: list[float] = []
    seen_matrix: set[str] = set()
    while pg.sup.state != "finished" and len(seen_x) < 200:
        seen_x.append(pg.centre(1)[0])
        seen_matrix.add(pg.transform(2))
        pg.page.wait_for_timeout(40)
    pg.wait_state("finished")
    assert len(set(seen_x)) > 5, seen_x
    assert seen_x == sorted(seen_x), "the ball must only move right"
    assert len(seen_matrix) > 5, "the rectangle should have turned through several angles"
    pg.settle()
    bx, _ = pg.to_screen(300, 0)
    assert abs(pg.centre(1)[0] - bx) < 1.5
    pg.shot("animated-end")


def test_background_and_guides(pg: Playground):
    pg.start(
        """
canvas(background="navy")
Grid(color="white", width=2, style="dashed")
Axis(color="yellow", size=100)
Circle(0, 0, radius=30, color="red", name="dot")
"""
    )
    pg.wait_state("finished")
    pg.settle()
    assert pg.page.locator("#background").get_attribute("fill") == "navy"
    sx, sy = pg.to_screen(-390, 290)
    assert pg.pixel(sx, sy) == (0, 0, 128)
    cx, cy = pg.to_screen(0, 0)
    assert pg.pixel(cx, cy) == (255, 0, 0)
    pg.shot("guides-on-navy")
    events = pg.page.evaluate("getComputedStyle(document.getElementById('guides')).pointerEvents")
    assert (
        events == "none"
        or pg.page.evaluate("getComputedStyle(document.querySelector('#guides > g')).pointerEvents")
        == "none"
    )
    labels = pg.page.eval_on_selector_all(
        "#guides g[data-type='axis'] text", "els => els.map(e => e.textContent)"
    )
    assert "100" in labels and "-100" in labels and "0" in labels


def test_canvas_background_can_change_live(pg: Playground):
    pg.start(
        """
canvas("black")
Circle(0, 0)
wait(0.3)
canvas("white")
while True:
    wait(0.1)
"""
    )
    pg.settle(900)
    sx, sy = pg.to_screen(-390, 290)
    assert pg.pixel(sx, sy) == (255, 255, 255)


def test_coordinates_plus_y_is_up_and_origin_is_the_centre(pg: Playground):
    pg.start(
        """
Circle(0, 0, radius=10, color="black")
Circle(100, 100, radius=10, color="red")
Circle(-100, -50, radius=10, color="blue")
"""
    )
    pg.wait_state("finished")
    pg.settle()
    ox, oy = pg.centre(1)
    rx, ry = pg.centre(2)
    bx, by = pg.centre(3)
    box = pg.canvas_box()
    scale = box["width"] / 800
    assert abs(ox - (box["x"] + box["width"] / 2)) < 1
    assert abs(oy - (box["y"] + box["height"] / 2)) < 1
    assert rx > ox and ry < oy
    assert abs((rx - ox) - 100 * scale) < 1 and abs((oy - ry) - 100 * scale) < 1
    assert bx < ox and by > oy
    assert abs((ox - bx) - 100 * scale) < 1 and abs((by - oy) - 50 * scale) < 1
    sx, sy = pg.to_screen(100, 100)
    assert pg.pixel(sx, sy) == (255, 0, 0)
    pg.shot("coordinates")


def test_line_triangle_and_text_sit_where_the_api_says(pg: Playground):
    pg.start(
        """
Line(-100, -100, 100, 100, width=6, color="green")
Triangle(0, 200, width=100, height=100, color="red")
Text("A", 200, -200, size=60, color="blue")
"""
    )
    pg.wait_state("finished")
    pg.settle()
    sx, sy = pg.to_screen(0, 0)
    assert pg.pixel(sx, sy) == (0, 128, 0)
    tx, ty = pg.to_screen(0, 235)
    assert pg.pixel(tx, ty) == (255, 0, 0)
    cx, cy = pg.to_screen(-45, 245)
    assert pg.pixel(cx, cy) != (255, 0, 0)
    bx, by = pg.to_screen(-45, 155)
    assert pg.pixel(bx, by) == (255, 0, 0)
    pg.shot("line-triangle-text")


def test_hide_show_remove_and_opacity(pg: Playground):
    pg.start(
        """
a = Circle(-100, 0, name="a")
b = Circle(0, 0, name="b")
c = Circle(100, 0, name="c")
wait(0.1)
a.hide()
b.opacity = 0.25
c.remove()
print("changed")
while True:
    wait(0.1)
"""
    )
    pg.wait_for_console("changed")
    expect(pg.shape(1)).to_be_hidden()
    assert pg.shape(2).evaluate("e => e.style.opacity") == "0.25"
    expect(pg.shape(3)).to_have_count(0)
