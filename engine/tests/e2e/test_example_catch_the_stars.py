"""The catch-the-stars example, run through the real supervisor, page and browser."""

from __future__ import annotations

import re
import time
from pathlib import Path

from e2e_helpers import Playground, poll

MAIN = Path(__file__).resolve().parents[3] / "examples" / "catch-the-stars" / "main.py"
SOURCE = MAIN.read_text(encoding="utf-8")


def short_game(seconds: float) -> str:
    source, count = re.subn(r"^GAME_SECONDS = \d+", f"GAME_SECONDS = {seconds}", SOURCE, flags=re.M)
    assert count == 1
    return source


def texts(pg: Playground) -> list[tuple[int, str]]:
    """(id, text) for every Text on the canvas, in drawing order."""
    return pg.page.evaluate(
        """() => [...window.__playground.nodes.entries()]
            .filter(([id, n]) => n.body && n.body.tagName === 'text')
            .map(([id, n]) => [id, n.body.textContent])"""
    )


def find_text(pg: Playground, pattern: str) -> int | None:
    for id, text in texts(pg):
        if re.fullmatch(pattern, text):
            return id
    return None


def stars(pg: Playground) -> list[int]:
    return [id for id, text in texts(pg) if text == "⭐"]


def score(pg: Playground) -> int:
    for _, text in texts(pg):
        if match := re.fullmatch(r"Score: (\d+)", text):
            return int(match.group(1))
    raise AssertionError("no score text on the canvas")


def wait_for_stars(pg: Playground) -> list[int]:
    poll(lambda: len(stars(pg)) >= 2, 10, "stars to appear")
    return stars(pg)


def test_the_real_example_starts_running_without_errors(pg: Playground):
    pg.start(SOURCE)
    pg.wait_state("running")
    wait_for_stars(pg)
    pg.shot("mid-game")
    assert not pg.page.locator("#error-panel").is_visible()
    assert find_text(pg, r"Score: 0") is not None


def test_arrow_keys_move_the_player_and_it_stays_on_the_canvas(pg: Playground):
    pg.start(SOURCE)
    pg.wait_state("running")
    player = pg.page.locator("#shapes > g[data-type='triangle']")

    def transform() -> str:
        return player.evaluate("e => getComputedStyle(e).transform")

    start = transform()
    pg.press("ArrowLeft")
    poll(lambda: transform() != start, 5, "the player to move left")
    left = transform()
    pg.press("ArrowRight")
    pg.press("ArrowRight")
    poll(lambda: transform() not in (start, left), 5, "the player to move right")

    for _ in range(40):
        pg.press("ArrowRight")
    pg.settle(500)
    box = player.bounding_box()
    canvas = pg.canvas_box()
    assert box is not None
    assert box["x"] + box["width"] <= canvas["x"] + canvas["width"]


def test_stars_fall(pg: Playground):
    pg.start(SOURCE)
    pg.wait_state("running")
    first = wait_for_stars(pg)[0]
    before = pg.transform(first)
    poll(lambda: pg.transform(first) != before, 5, "a star to move")


def click_a_star(pg: Playground) -> int | None:
    """Click a star that is in the upper half of the canvas; return its id."""
    half = pg.canvas_box()["height"] / 2
    for id in stars(pg):
        box = pg.shape(id).bounding_box()
        if box and 40 < box["y"] + box["height"] / 2 < half:
            x, y = pg.centre(id)
            pg.page.mouse.click(x, y)
            return id
    return None


def test_clicking_a_star_pops_it_for_a_bonus(pg: Playground):
    pg.start(SOURCE)
    pg.wait_state("running")
    wait_for_stars(pg)
    deadline = time.monotonic() + 15
    while score(pg) < 2 and time.monotonic() < deadline:
        click_a_star(pg)  # stars move, so a click can miss: just try again
        pg.settle(100)
    assert score(pg) >= 2


def test_catching_a_star_with_the_player_scores(pg: Playground):
    pg.start(SOURCE)
    pg.wait_state("running")
    player = pg.page.locator("#shapes > g[data-type='triangle']")
    deadline = time.monotonic() + 20
    while score(pg) == 0 and time.monotonic() < deadline:
        mine = player.bounding_box()
        lowest = None
        for id in stars(pg):
            box = pg.shape(id).bounding_box()
            above = mine is not None and box is not None and box["y"] < mine["y"]
            if box and above and (lowest is None or box["y"] > lowest["y"]):
                lowest = box
        if lowest and mine:
            offset = (lowest["x"] + lowest["width"] / 2) - (mine["x"] + mine["width"] / 2)
            if offset < -20:
                pg.press("ArrowLeft")
            elif offset > 20:
                pg.press("ArrowRight")
        pg.page.wait_for_timeout(40)
    assert score(pg) > 0


def test_a_short_game_ends_with_game_over_and_the_program_finishes(pg: Playground):
    pg.start(short_game(2))
    pg.wait_state("running")
    pg.wait_state("finished")
    pg.wait_for_console("Final score:")
    final = None
    for _, text in texts(pg):
        if match := re.fullmatch(r"Game over! Score: (\d+)", text):
            final = int(match.group(1))
    assert final is not None, "no Game over text"
    assert re.search(rf"Final score: {final}\b", pg.console())
    assert not pg.page.locator("#error-panel").is_visible()
    assert "Program finished" in pg.page.locator("#status").inner_text()
    pg.shot("game-over")
