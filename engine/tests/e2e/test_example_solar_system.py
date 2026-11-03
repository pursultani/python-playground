"""The solar-system example, run from its real file through the whole stack."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from core.supervisor import Supervisor
from e2e_helpers import Playground, poll
from playwright.sync_api import Browser

EXAMPLE = Path(__file__).resolve().parents[3] / "examples" / "solar-system" / "main.py"


@pytest.fixture
def solar(chromium: Browser, request) -> Iterator[Playground]:
    pg = Playground(EXAMPLE.parent, chromium, request.node.name)
    pg.script = EXAMPLE
    pg.supervisor = Supervisor(EXAMPLE, port=0, poll_interval=0.05, log=pg.logs.append)
    pg.supervisor.start()
    pg.open_page()
    yield pg
    pg.close()
    assert pg.js_errors == [], "JavaScript errors in the page"
    assert pg.console_errors == [], "console errors in the page"


def node_id(pg: Playground, title: str) -> int:
    ids = pg.page.evaluate(
        "t => [...window.__playground.nodes].filter(([id, n]) => n.title && "
        "n.title.textContent === t).map(([id]) => id)",
        title,
    )
    assert len(ids) == 1, ids
    return ids[0]


def grid_display(pg: Playground) -> str:
    return pg.page.evaluate(
        "() => getComputedStyle(document.querySelector('#guides > g[data-type=grid]')).display"
    )


def test_runs_and_draws_the_sun_planets_and_moon(solar):
    solar.wait_state("running")
    assert solar.page.locator("#error-panel").is_hidden()
    circles = solar.page.locator("#shapes > g[data-type='circle']")
    poll(lambda: circles.count() >= 20, 10, "all the circles")
    sun = node_id(solar, "Sun")
    names = ["Mercury", "Venus", "Earth", "Mars", "Jupiter", "Saturn"]
    for name in names:
        node_id(solar, name)
    box = solar.canvas_box()
    for id in [sun, *(node_id(solar, n) for n in names)]:
        cx, cy = solar.centre(id)
        assert box["x"] <= cx <= box["x"] + box["width"]
        assert box["y"] <= cy <= box["y"] + box["height"]
    solar.settle(600)
    solar.shot("solar")


def test_planets_move(solar):
    solar.wait_state("running")
    earth = node_id(solar, "Earth")
    before = solar.transform(earth)
    poll(lambda: solar.transform(earth) != before, 5, "Earth to move")
    solar.wait_state("running")
    assert solar.page.locator("#error-panel").is_hidden()


def test_g_shows_and_hides_the_grid_while_everything_keeps_moving(solar):
    solar.wait_state("running")
    assert grid_display(solar) == "none"
    mercury = node_id(solar, "Mercury")

    solar.press("g")
    poll(lambda: grid_display(solar) != "none", 5, "the grid to appear")
    solar.shot("grid-on")
    seen = solar.transform(mercury)
    poll(lambda: solar.transform(mercury) != seen, 5, "Mercury to keep moving")

    solar.press("g")
    poll(lambda: grid_display(solar) == "none", 5, "the grid to hide")
    seen = solar.transform(mercury)
    poll(lambda: solar.transform(mercury) != seen, 5, "Mercury to keep moving")
    solar.wait_state("running")
    assert solar.page.locator("#error-panel").is_hidden()
