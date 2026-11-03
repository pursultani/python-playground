"""SVG rendering model: shapes, guides, titles, transforms."""

from __future__ import annotations

import pytest
from page_driver import App, create, frame, remove, update
from playwright.sync_api import expect


def transform(app: App, id: int) -> str:
    return app.shape(id).evaluate("e => e.style.transform")


def test_circle(app: App) -> None:
    app.send(frame(create(1, "circle", x=100, y=50, radius=30, color="tomato", rotation=0)))
    group = app.shape(1)
    expect(group).to_have_attribute("data-type", "circle")
    circle = group.locator("circle")
    expect(circle).to_have_attribute("r", "30")
    expect(circle).to_have_attribute("fill", "tomato")
    assert transform(app, 1) == "translate(100px, -50px) rotate(0deg)"


def test_y_axis_is_flipped_and_rotation_is_counter_clockwise(app: App) -> None:
    app.send(frame(create(1, "rectangle", x=-20, y=70, width=40, height=20, rotation=30)))
    expect(app.shape(1)).to_have_attribute("data-type", "rectangle")
    assert transform(app, 1) == "translate(-20px, -70px) rotate(-30deg)"
    rect = app.shape(1).locator("rect")
    assert rect.get_attribute("x") == "-20"
    assert rect.get_attribute("y") == "-10"
    assert rect.get_attribute("width") == "40"
    assert rect.get_attribute("height") == "20"


def test_counter_clockwise_rotation_on_screen(app: App) -> None:
    app.send(frame(create(1, "rectangle", x=0, y=0, width=100, height=10, rotation=90)))
    expect(app.shape(1)).to_have_attribute("data-type", "rectangle")
    app.page.wait_for_timeout(200)
    box = app.shape(1).locator("rect").bounding_box()
    assert box is not None
    assert box["height"] > box["width"]
    # rotating the right end of a horizontal bar 90 degrees CCW moves it up the screen
    app.send(frame(create(2, "line", x=0, y=0, x2=0, y2=100, width=4)))
    line = app.shape(2).locator("line")
    assert line.get_attribute("y2") == "-100"


def test_triangle_apex_points_up(app: App) -> None:
    app.send(frame(create(1, "triangle", x=0, y=0, width=80, height=60)))
    poly = app.shape(1).locator("polygon")
    expect(poly).to_have_attribute("points", "0,-30 40,30 -40,30")


def test_line_geometry_and_no_rotation(app: App) -> None:
    app.send(
        frame(create(1, "line", x=10, y=20, x2=110, y2=-30, width=5, color="green", rotation=45))
    )
    group = app.shape(1)
    line = group.locator("line")
    expect(line).to_have_attribute("x2", "100")
    expect(line).to_have_attribute("y2", "50")
    expect(line).to_have_attribute("stroke", "green")
    expect(line).to_have_attribute("stroke-width", "5")
    expect(line).to_have_attribute("stroke-linecap", "round")
    assert transform(app, 1) == "translate(10px, -20px)"


def test_text(app: App) -> None:
    app.send(frame(create(1, "text", x=0, y=0, text="Hello 🌍", size=40, color="purple")))
    text = app.shape(1).locator("text")
    expect(text).to_have_text("Hello 🌍")
    expect(text).to_have_attribute("font-size", "40")
    expect(text).to_have_attribute("text-anchor", "middle")
    expect(text).to_have_attribute("fill", "purple")


def test_update_and_remove(app: App) -> None:
    app.send(frame(create(1, "circle", x=0, y=0, radius=30), create(2, "circle", x=5, y=5)))
    expect(app.shapes()).to_have_count(2)
    app.send(frame(update(1, x=40, radius=45, color="red", opacity=0.4)))
    expect(app.shape(1).locator("circle")).to_have_attribute("r", "45")
    expect(app.shape(1).locator("circle")).to_have_attribute("fill", "red")
    assert transform(app, 1).startswith("translate(40px, 0px)")
    assert app.shape(1).evaluate("e => e.style.opacity") == "0.4"
    app.send(frame(remove(1)))
    expect(app.shapes()).to_have_count(1)
    assert app.ids() == [2]


def test_visible_false_hides(app: App) -> None:
    app.send(frame(create(1, "circle", x=0, y=0, visible=False)))
    expect(app.shape(1)).to_have_attribute("data-id", "1")
    assert app.shape(1).evaluate("e => e.style.display") == "none"
    app.send(frame(update(1, visible=True)))
    expect(app.shape(1)).to_be_visible()


def test_title_with_halo_and_hidden_when_empty(app: App) -> None:
    app.send(frame(create(1, "circle", x=0, y=0, radius=60, title="Ball")))
    title = app.shape(1).locator("text.title")
    expect(title).to_have_text("Ball")
    style = title.evaluate(
        "e => { const s = getComputedStyle(e);"
        " return [s.paintOrder, s.strokeWidth, s.pointerEvents]; }"
    )
    assert style[0].startswith("stroke")
    assert style[1] == "3px"
    assert style[2] == "none"
    app.send(frame(update(1, title="")))
    expect(title).to_be_hidden()


def test_line_title_sits_at_the_midpoint(app: App) -> None:
    app.send(frame(create(1, "line", x=0, y=0, x2=100, y2=60, title="mid")))
    title = app.shape(1).locator("text.title")
    expect(title).to_have_attribute("x", "50")
    expect(title).to_have_attribute("y", "-30")


def test_text_shapes_have_no_title_element(app: App) -> None:
    app.send(frame(create(1, "text", x=0, y=0, text="hi", title="ignored")))
    expect(app.shape(1)).to_have_attribute("data-type", "text")
    expect(app.shape(1).locator("text.title")).to_have_count(0)


def test_grid_lines_and_styles(app: App) -> None:
    app.send(frame(create(1, "grid", color="gray", width=2, size=100, style="dashed", opacity=0.5)))
    path = app.shape(1).locator("path")
    expect(path).to_have_attribute("stroke", "gray")
    expect(path).to_have_attribute("stroke-width", "2")
    expect(path).to_have_attribute("stroke-dasharray", "8 6")
    d = path.get_attribute("d") or ""
    # lines at every multiple of 100 across the canvas, origin lines included
    assert d.count("V") == 9
    assert d.count("H") == 7
    assert "M0 -300V300" in d
    assert app.shape(1).evaluate("e => e.style.opacity") == "0.5"
    app.send(frame(update(1, style="dotted")))
    expect(path).to_have_attribute("stroke-dasharray", "1 5")
    expect(path).to_have_attribute("stroke-linecap", "round")


def test_axis_numbers_have_a_halo_in_the_canvas_colour(app: App) -> None:
    app.send(
        {"t": "canvas", "background": "navy"},
        frame(create(1, "axis", color="yellow", width=3, size=100, style="solid", labels=True)),
    )
    app.sync()
    label = app.shape(1).locator("text").first
    assert label.evaluate("e => getComputedStyle(e).stroke") == "rgb(0, 0, 128)"
    assert label.evaluate("e => getComputedStyle(e).paintOrder") == "stroke"


def test_axis_ticks_and_labels(app: App) -> None:
    app.send(frame(create(1, "axis", color="gray", width=3, size=100, style="solid", labels=True)))
    labels = app.shape(1).locator("g text")
    expect(labels.first).to_be_attached()
    texts = labels.evaluate_all("els => els.map(e => e.textContent)")
    assert {"100", "200", "300", "-100", "-200", "-300", "0"} <= set(texts)
    assert texts.count("0") == 1
    # y labels are positive upward: the "100" label on the y axis is above the origin
    ys = app.shape(1).evaluate(
        """e => [...e.querySelectorAll('g text')]
            .filter(t => t.textContent === '200' && t.getAttribute('text-anchor') === 'end')
            .map(t => Number(t.getAttribute('y')))"""
    )
    assert ys == [-200]
    app.send(frame(update(1, labels=False)))
    expect(labels).to_have_count(0)
    d = app.shape(1).locator("path").nth(1).get_attribute("d") or ""
    assert d.count("V4") == 8


def test_guides_are_behind_shapes_and_ignore_clicks(app: App) -> None:
    app.send(frame(create(1, "circle", x=0, y=0), create(2, "grid"), create(3, "axis")))
    expect(app.page.locator("#guides > g")).to_have_count(2)
    expect(app.shapes()).to_have_count(1)
    order = app.page.evaluate("[...document.querySelectorAll('#canvas > *')].map(e => e.id)")
    assert order == ["background", "guides", "shapes"]
    pe = app.page.evaluate("getComputedStyle(document.getElementById('guides')).pointerEvents")
    assert pe == "none"


def test_stacking_follows_creation_order(app: App) -> None:
    app.send(frame(create(1, "circle"), create(2, "rectangle"), create(3, "triangle")))
    expect(app.shapes()).to_have_count(3)
    order = app.page.evaluate(
        "[...document.querySelectorAll('#shapes > g')].map(e => e.dataset.id)"
    )
    assert order == ["1", "2", "3"]


def test_unknown_types_and_props_are_ignored(app: App) -> None:
    app.send(
        frame(
            create(1, "hexagon", x=0, y=0),
            create(2, "circle", x=0, y=0, sparkle=True),
            update(99, x=3),
        )
    )
    app.sync()
    assert app.ids() == [2]


@pytest.mark.parametrize("scale", [1])
def test_canvas_is_4_to_3_and_centred(app: App, scale: int) -> None:
    box = app.page.locator("#canvas-wrap").bounding_box()
    assert box is not None
    assert abs(box["width"] / box["height"] - 4 / 3) < 0.01
    viewport = app.page.viewport_size
    assert viewport is not None
    centre = box["x"] + box["width"] / 2
    assert abs(centre - viewport["width"] / 2) < 2
    assert app.page.locator("#canvas").get_attribute("viewBox") == "-400 -300 800 600"
