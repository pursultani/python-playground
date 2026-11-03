"""Live refresh: saving the file re-runs the program without flicker."""

from __future__ import annotations

from e2e_helpers import Playground
from playwright.sync_api import expect

V1 = """
canvas("lightyellow")
Circle(-100, 0, color="tomato", name="a")
Rectangle(100, 0, color="gold", name="b")
Text("three", 0, 100, name="c")
print("v1")
while True:
    wait(0.1)
"""

V2 = """
canvas("lightyellow")
Circle(-100, 100, color="seagreen", name="a")
Rectangle(100, 0, color="gold", name="b")
print("v2")
while True:
    wait(0.1)
"""

OBSERVE_REMOVALS = """
() => {
  window.__removed = [];
  new MutationObserver((records) => {
    for (const r of records) for (const n of r.removedNodes) {
      if (n.dataset && n.dataset.id) window.__removed.push(n.dataset.id);
    }
  }).observe(document.getElementById('shapes'), {childList: true});
}
"""


def test_edit_triggers_a_new_run_and_reuses_unchanged_nodes(pg: Playground):
    pg.start(V1)
    pg.wait_for_console("v1")
    assert pg.ids() == [1, 2, 3]
    pg.tag(1, "a")
    pg.tag(2, "b")
    pg.tag(3, "c")
    pg.page.evaluate(OBSERVE_REMOVALS)
    run = pg.edit(V2, "running")
    assert run == 2
    pg.wait_for_console("v2")
    assert pg.console() == "v2\n"
    assert pg.is_same_node(1, "a"), "node 1 must be reused, not recreated"
    assert pg.is_same_node(2, "b")
    expect(pg.shape(3)).to_have_count(0)
    assert pg.ids() == [1, 2], "the object the program no longer creates disappears"
    removed = pg.page.evaluate("window.__removed")
    assert removed == ["3"], f"only the stale node may be removed, got {removed}"
    assert pg.shape(1).locator("circle").get_attribute("fill") == "seagreen"
    pg.settle()
    # the circle glided up to its new place: y=100 is above the centre
    _, cy = pg.centre(1)
    box = pg.canvas_box()
    assert cy < box["y"] + box["height"] / 2
    pg.shot("after-edit")


def test_rerunning_an_identical_script_does_not_touch_the_dom(pg: Playground):
    pg.start(V1)
    pg.wait_for_console("v1")
    pg.page.evaluate(OBSERVE_REMOVALS)
    pg.page.evaluate(
        """() => {
          window.__adds = 0;
          new MutationObserver((r) => { window.__adds += r.length; })
            .observe(document.getElementById('shapes'), {childList: true});
        }"""
    )
    pg.edit(V1 + "\n# a comment\n", "running")
    pg.wait_for_console("v1")
    pg.settle()
    assert pg.page.evaluate("window.__removed") == []
    assert pg.page.evaluate("window.__adds") == 0
    assert pg.ids() == [1, 2, 3]


def test_unchanged_shapes_do_not_blink_between_runs(pg: Playground):
    pg.start(V1)
    pg.wait_for_console("v1")
    pg.page.evaluate(
        """() => {
          window.__hidden = 0;
          const el = document.querySelector('#shapes > g[data-id="1"]');
          const check = () => {
            if (!el.isConnected || getComputedStyle(el).display === 'none') window.__hidden++;
            requestAnimationFrame(check);
          };
          check();
        }"""
    )
    for i in range(3):
        pg.edit(V1 + f"\n# edit {i}\n", "running")
    pg.settle()
    assert pg.page.evaluate("window.__hidden") == 0


def test_a_shape_that_changes_type_is_replaced(pg: Playground):
    pg.start("Circle(name='x')\nwhile True:\n    wait(0.1)\n")
    pg.wait_state("running")
    pg.tag(1)
    pg.edit("Rectangle(name='x')\nwhile True:\n    wait(0.1)\n", "running")
    assert pg.shape(1).get_attribute("data-type") == "rectangle"
    assert not pg.is_same_node(1)
    assert pg.ids() == [1]


def test_background_resets_to_white_on_rerun(pg: Playground):
    pg.start("canvas('black')\nwhile True:\n    wait(0.1)\n")
    pg.wait_state("running")
    pg.settle()
    assert pg.page.locator("#background").get_attribute("fill") == "black"
    pg.edit("Circle()\nwhile True:\n    wait(0.1)\n", "running")
    pg.settle()
    assert pg.page.locator("#background").get_attribute("fill") == "white"


def test_stale_objects_are_removed_when_the_new_run_finishes_instantly(pg: Playground):
    pg.start("for i in range(5):\n    Circle(i * 50, 0)\nwhile True:\n    wait(0.1)\n")
    pg.wait_state("running")
    expect(pg.shapes()).to_have_count(5)
    pg.edit("Circle()\n", "finished")
    expect(pg.shapes()).to_have_count(1)


def test_stale_objects_are_removed_when_the_new_run_crashes_before_drawing(pg: Playground):
    pg.start("for i in range(5):\n    Circle(i * 50, 0)\nwhile True:\n    wait(0.1)\n")
    pg.wait_state("running")
    expect(pg.shapes()).to_have_count(5)
    pg.edit("oops\n", "crashed")
    expect(pg.shapes()).to_have_count(0)


def test_stacking_order_follows_creation_order_after_a_rerun(pg: Playground):
    pg.start("Circle(0, 0, color='red')\nCircle(30, 0, color='blue')\nwhile True:\n    wait(0.1)\n")
    pg.wait_state("running")
    pg.edit(
        "Circle(0, 0, color='red')\nCircle(30, 0, color='blue')\nCircle(60, 0, color='green')\n"
        "while True:\n    wait(0.1)\n",
        "running",
    )
    expect(pg.shapes()).to_have_count(3)
    ids = pg.page.eval_on_selector_all("#shapes > g", "els => els.map(e => e.dataset.id)")
    assert ids == ["1", "2", "3"]


def test_restart_button_reruns_the_program(pg: Playground):
    pg.start("print('hi')\nCircle()\nwhile True:\n    wait(0.1)\n")
    pg.wait_for_console("hi")
    pg.page.click("#restart")
    expect(pg.body()).to_have_attribute("data-run", "2")
    pg.wait_for_console("hi")
    assert pg.console() == "hi\n"
    assert pg.sup.run == 2


def test_rapid_saves_end_on_the_latest_version(pg: Playground):
    pg.start("print('v0')\nwhile True:\n    wait(0.1)\n")
    pg.wait_for_console("v0")
    for i in range(1, 6):
        pg.script.write_text(f"print('v{i}')\nwhile True:\n    wait(0.1)\n")
    pg.wait_for_console("v5")
    pg.wait_state("running")
    assert pg.console() == "v5\n"


def test_editing_a_second_file_restarts(pg: Playground):
    (pg.directory / "helper.py").write_text("VALUE = 1\n")
    pg.start("import helper\nprint(helper.VALUE)\nwhile True:\n    wait(0.1)\n")
    pg.wait_for_console("1")
    (pg.directory / "helper.py").write_text("VALUE = 22\n")
    pg.wait_for_console("22")


SAMPLE_BACKGROUND = """
() => {
  window.__fills = [];
  const bg = document.getElementById('background');
  const sample = () => {
    window.__fills.push(getComputedStyle(bg).fill);
    window.__sampler = requestAnimationFrame(sample);
  };
  sample();
}
"""

DARK = "rgb(11, 16, 38)"
DARK_SCRIPT = (
    "canvas(background='#0b1026')\nCircle(color='gold')\nprint('{}')\nwhile True:\n    wait(0.05)\n"
)


def test_editing_a_dark_program_never_flashes_white(pg: Playground):
    pg.start(DARK_SCRIPT.format("v1"))
    pg.wait_for_console("v1")
    pg.settle()
    pg.page.evaluate(SAMPLE_BACKGROUND)
    for i in range(2, 5):
        pg.edit(DARK_SCRIPT.format(f"v{i}"), "running")
        pg.wait_for_console(f"v{i}")
        pg.settle(150)
    fills = pg.page.evaluate("cancelAnimationFrame(window.__sampler) || window.__fills")
    assert len(fills) > 30
    assert set(fills) == {DARK}, f"background changed during re-runs: {sorted(set(fills))}"


def test_dropping_the_canvas_call_goes_back_to_white_without_a_fade(pg: Playground):
    pg.start(DARK_SCRIPT.format("v1"))
    pg.wait_for_console("v1")
    pg.settle()
    pg.page.evaluate(SAMPLE_BACKGROUND)
    pg.edit("Circle()\nprint('v2')\nwhile True:\n    wait(0.05)\n", "running")
    pg.wait_for_console("v2")
    pg.settle(150)
    fills = pg.page.evaluate("cancelAnimationFrame(window.__sampler) || window.__fills")
    assert set(fills) == {DARK, "rgb(255, 255, 255)"}, sorted(set(fills))
    assert fills[-1] == "rgb(255, 255, 255)"
