"""Run boundaries, node reuse and transitions."""

from __future__ import annotations

from page_driver import App, create, error, frame, print_, run, status, update
from playwright.sync_api import expect

WATCH_TRANSITIONS = """
window.__transitions = [];
document.addEventListener("transitionrun", (e) => {
  const g = e.target.closest ? e.target.closest("[data-id]") : null;
  if (g) window.__transitions.push([g.dataset.id, e.propertyName]);
});
"""


def two_shapes(app: App) -> None:
    app.send(frame(create(1, "circle", x=0, y=0, radius=30), create(2, "rectangle", x=5, y=5)))
    expect(app.shapes()).to_have_count(2)


def tag(app: App, id: int) -> None:
    app.shape(id).evaluate("e => { e.__mine = true; }")


def is_tagged(app: App, id: int) -> bool:
    return app.shape(id).evaluate("e => e.__mine === true")


def test_run_keeps_nodes_until_first_frame(app: App) -> None:
    two_shapes(app)
    app.send(
        print_("old output\n"),
        {"t": "canvas", "background": "red"},
        error("Oops", "x", frames=[], context=[]),
    )
    app.sync()
    expect(app.page.locator("#error-panel")).to_be_visible()
    app.send(run(2), status("starting", 2))
    app.sync()
    assert app.ids() == [1, 2]
    app.expect_state("starting")
    expect(app.page.locator("#error-panel")).to_be_hidden()
    assert app.console_text() == ""
    expect(app.page.locator("#background")).to_have_attribute("fill", "red")
    app.send(status("running", 2))
    app.sync()
    assert app.ids() == [1, 2]
    expect(app.page.locator("#background")).to_have_attribute("fill", "red")


def background(app: App) -> str:
    return app.page.locator("#background").get_attribute("fill") or ""


def dark_page(app: App) -> None:
    app.send({"t": "canvas", "background": "#0b1026"}, frame(create(1, "circle")))
    expect(app.shapes()).to_have_count(1)
    assert background(app) == "#0b1026"


def test_run_keeps_the_background_until_the_first_frame_then_resets_to_white(app: App) -> None:
    dark_page(app)
    app.send(run(2), status("starting", 2), status("running", 2), print_("hi\n"))
    app.sync()
    assert background(app) == "#0b1026"
    app.send(frame(create(1, "circle")))
    app.sync()
    assert background(app) == "white"


def test_canvas_message_first_applies_its_background_and_frame_does_not_undo_it(app: App) -> None:
    dark_page(app)
    app.send(run(2), {"t": "canvas", "background": "#102030"})
    app.sync()
    assert background(app) == "#102030"
    assert app.ids() == [1]
    app.send(frame(create(1, "circle")), frame(update(1, x=5)))
    app.sync()
    assert background(app) == "#102030"


def test_canvas_and_frame_in_one_flush_keep_the_new_background(app: App) -> None:
    dark_page(app)
    app.send(run(2), {"t": "canvas", "background": "#102030"}, frame(create(1, "circle")))
    app.sync()
    assert background(app) == "#102030"


def test_run_that_finishes_immediately_resets_the_background(app: App) -> None:
    dark_page(app)
    app.send(run(2), status("starting", 2))
    app.sync()
    assert background(app) == "#0b1026"
    app.send(status("finished", 2))
    app.sync()
    assert background(app) == "white"


def test_end_and_error_also_reset_the_background(app: App) -> None:
    dark_page(app)
    app.send(run(2), {"t": "end"})
    app.sync()
    assert background(app) == "white"
    app.send({"t": "canvas", "background": "#0b1026"}, run(3), error("Oops", "x"))
    app.sync()
    assert background(app) == "white"


def test_later_canvas_calls_in_the_same_run_are_not_reset(app: App) -> None:
    dark_page(app)
    app.send(run(2), frame(create(1, "circle")))
    app.send({"t": "canvas", "background": "#102030"}, frame(update(1, x=5)))
    app.sync()
    assert background(app) == "#102030"


def test_snapshot_cancels_a_pending_background_reset(app: App) -> None:
    dark_page(app)
    app.send(run(2))
    app.sync()
    app.host.snapshot.update(background="#102030", run=3)
    app.host.drop_clients()
    app.page.wait_for_function("document.body.dataset.run === '3'")
    app.send(frame(create(1, "circle")))
    app.sync()
    assert background(app) == "#102030"


def test_rerun_reuses_nodes_and_sweeps_stale_ones_on_first_frame(app: App) -> None:
    two_shapes(app)
    tag(app, 1)
    app.send(run(2), status("starting", 2), status("running", 2))
    app.send(frame(create(1, "circle", x=50, y=0, radius=30)))
    app.sync()
    assert app.ids() == [1]
    assert is_tagged(app, 1)
    assert app.shape(1).evaluate("e => e.style.transform").startswith("translate(50px")


def test_create_with_different_type_replaces_the_element(app: App) -> None:
    two_shapes(app)
    tag(app, 1)
    app.send(run(2), frame(create(1, "rectangle", x=0, y=0), create(2, "rectangle", x=5, y=5)))
    app.sync()
    expect(app.shape(1)).to_have_attribute("data-type", "rectangle")
    assert not is_tagged(app, 1)


def test_finished_sweeps_stale_nodes(app: App) -> None:
    two_shapes(app)
    app.send(run(2), status("starting", 2), status("running", 2), status("finished", 2))
    expect(app.shapes()).to_have_count(0)
    app.expect_state("finished")


def test_error_sweeps_stale_nodes_and_crash_keeps_drawing(app: App) -> None:
    two_shapes(app)
    app.send(
        run(2),
        frame(create(1, "circle", x=0, y=0)),
        error("ValueError", "bad", frames=[], context=[]),
        status("crashed", 2),
    )
    app.expect_state("crashed")
    assert app.ids() == [1]
    expect(app.page.locator("#error-panel")).to_be_visible()


def test_sweep_only_happens_once_per_run(app: App) -> None:
    two_shapes(app)
    app.send(run(2), frame(create(1, "circle", x=0, y=0)))
    app.sync()
    app.send(frame(create(3, "circle", x=0, y=0)))
    app.sync()
    assert app.ids() == [1, 3]


def test_restack_after_sweep_keeps_creation_order(app: App) -> None:
    app.send(frame(create(1, "circle"), create(2, "circle"), create(3, "circle")))
    expect(app.shapes()).to_have_count(3)
    app.send(run(2), frame(create(3, "circle"), create(2, "circle")))
    app.sync()
    order = app.page.evaluate(
        "[...document.querySelectorAll('#shapes > g')].map(e => e.dataset.id)"
    )
    assert order == ["2", "3"]


def test_stale_status_from_older_run_is_ignored(app: App) -> None:
    app.send(run(5), status("running", 5), status("finished", 4))
    app.sync()
    app.expect_state("running")


def test_first_paint_has_no_transition_but_updates_animate(app: App) -> None:
    app.page.evaluate(WATCH_TRANSITIONS)
    app.send(frame(create(1, "circle", x=0, y=0, radius=30, color="red")))
    expect(app.shape(1)).to_have_attribute("data-type", "circle")
    app.page.wait_for_timeout(300)
    assert app.page.evaluate("window.__transitions") == []
    assert not app.shape(1).evaluate("e => e.classList.contains('no-anim')")
    duration = app.shape(1).evaluate("e => getComputedStyle(e).transitionDuration")
    assert "0.12s" in duration
    app.send(frame(update(1, x=100, color="blue")))
    app.sync()
    app.page.wait_for_function("window.__transitions.length > 0")
    names = {name for _id, name in app.page.evaluate("window.__transitions")}
    assert "transform" in names


def test_recreating_an_existing_node_animates(app: App) -> None:
    app.send(frame(create(1, "circle", x=0, y=0)))
    expect(app.shape(1)).to_have_attribute("data-type", "circle")
    app.page.wait_for_timeout(100)
    app.page.evaluate(WATCH_TRANSITIONS)
    app.send(run(2), frame(create(1, "circle", x=200, y=0)))
    app.page.wait_for_function("window.__transitions.length > 0")
