"""The first paint (and every snapshot) must already look final: no fades, no dimming, no flash."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fake_host import FakeHost
from page_driver import App, create, error, run, status
from playwright.sync_api import Browser, expect

SAMPLER = """
(() => {
  window.__frames = [];
  const t0 = performance.now();
  const wrap = () => document.getElementById("canvas-wrap");
  function sample() {
    const w = wrap();
    const bg = document.getElementById("background");
    const badge = document.getElementById("status");
    if (w && bg && badge) {
      const cs = getComputedStyle(w);
      window.__frames.push({
        t: performance.now() - t0,
        ready: "ready" in document.body.dataset,
        hasError: document.body.classList.contains("has-error"),
        visibility: cs.visibility,
        opacity: parseFloat(cs.opacity),
        filter: cs.filter,
        fill: getComputedStyle(bg).fill,
        badge: getComputedStyle(badge).backgroundColor,
        badgeText: getComputedStyle(badge).color,
        state: document.body.dataset.state,
      });
    }
    requestAnimationFrame(sample);
  }
  requestAnimationFrame(sample);
})();
"""

# Only listens (never reads styles), so it cannot force the style flushes that hide real bugs.
TRANSITION_LOG = """
window.__transitions = [];
document.addEventListener("transitionrun", (e) => {
  const t = e.target;
  window.__transitions.push((t.id || t.className.baseVal || t.className) + ":" + e.propertyName);
}, true);
"""

NAVY = "rgb(11, 16, 38)"
GREEN_BG = "rgb(228, 247, 234)"
GREEN = "rgb(23, 163, 74)"
DARK_SNAPSHOT: dict[str, Any] = {
    "background": "#0b1026",
    "objects": [{"id": 1, "type": "circle", "props": {"x": 0, "y": 0, "radius": 40}}],
}


@pytest.fixture
def sampled(chromium: Browser, host: FakeHost) -> Iterator[App]:
    context = chromium.new_context(viewport={"width": 1100, "height": 800})
    page = context.new_page()
    page.set_default_timeout(5000)
    app = App(host, page)
    page.add_init_script(SAMPLER)
    yield app
    context.close()
    assert app.js_errors == []


@pytest.fixture
def listening(chromium: Browser, host: FakeHost) -> Iterator[App]:
    context = chromium.new_context(viewport={"width": 1100, "height": 800})
    page = context.new_page()
    page.set_default_timeout(5000)
    app = App(host, page)
    page.add_init_script(TRANSITION_LOG)
    yield app
    context.close()
    assert app.js_errors == []


def transitions(app: App) -> list[str]:
    return app.page.evaluate("window.__transitions")


def frames(app: App) -> list[dict[str, Any]]:
    return app.page.evaluate("window.__frames")


def ready_frames(app: App) -> list[dict[str, Any]]:
    return [f for f in frames(app) if f["ready"]]


def settle(app: App, ms: int = 450) -> None:
    app.page.wait_for_timeout(ms)


def test_first_paint_is_final_look(sampled: App) -> None:
    sampled.host.snapshot.update(DARK_SNAPSHOT)
    sampled.open()
    settle(sampled)
    shown = ready_frames(sampled)
    assert shown
    for f in shown:
        assert f["state"] == "running"
        assert f["opacity"] == 1 and f["filter"] == "none"
        assert f["fill"] == NAVY
        assert (f["badge"], f["badgeText"]) == (GREEN_BG, GREEN)


def test_canvas_stays_hidden_until_the_first_message(sampled: App) -> None:
    sampled.host.snapshot.update(DARK_SNAPSHOT)
    sampled.open()
    settle(sampled)
    assert all(f["visibility"] == "hidden" for f in frames(sampled) if not f["ready"])
    assert all(f["visibility"] == "visible" for f in ready_frames(sampled))


def test_snapshot_with_error_is_dimmed_from_the_first_frame(sampled: App) -> None:
    sampled.host.snapshot.update(
        DARK_SNAPSHOT,
        state="crashed",
        error=error("NameError", "oops", frames=[], context=[]),
    )
    sampled.open()
    settle(sampled)
    shown = ready_frames(sampled)
    assert shown
    for f in shown:
        assert f["hasError"] and f["opacity"] == pytest.approx(0.45)
    panel_animations = sampled.page.evaluate(
        "document.getAnimations().filter(a => a.animationName === 'drop-in').length"
    )
    assert panel_animations == 0


def test_reconnect_snapshot_does_not_dim_or_fade(sampled: App) -> None:
    sampled.host.snapshot.update(DARK_SNAPSHOT)
    sampled.open()
    settle(sampled, 100)
    before = len(frames(sampled))
    sampled.host.snapshot = {**sampled.host.snapshot, "background": "#102030", "run": 2}
    sampled.host.drop_clients()
    sampled.page.wait_for_function("document.body.dataset.run === '2'")
    settle(sampled)
    for f in frames(sampled)[before:]:
        if f["ready"]:
            assert f["opacity"] == 1 and f["filter"] == "none"
            assert f["fill"] in {NAVY, "rgb(16, 32, 48)"}
    assert frames(sampled)[-1]["fill"] == "rgb(16, 32, 48)"


def test_rerun_without_error_never_dims_the_canvas(sampled: App) -> None:
    sampled.host.snapshot.update(DARK_SNAPSHOT)
    sampled.open()
    sampled.send(run(2), status("starting", 2), status("running", 2))
    sampled.sync()
    settle(sampled, 100)
    sampled.send(
        {"t": "frame", "ops": [create(1, "circle", x=5, y=5, radius=10)]},
        {"t": "canvas", "background": "#0b1026"},
    )
    sampled.sync()
    settle(sampled)
    assert all(f["opacity"] == 1 and f["filter"] == "none" for f in ready_frames(sampled))


def test_rerun_resets_background_without_a_fade(sampled: App) -> None:
    sampled.host.snapshot.update(DARK_SNAPSHOT)
    sampled.open()
    settle(sampled, 100)
    before = len(frames(sampled))
    sampled.send(run(2), status("starting", 2))
    sampled.sync()
    settle(sampled)
    after = [f["fill"] for f in frames(sampled)[before:]]
    assert after[-1] == "rgb(255, 255, 255)"
    # no in-between greys: every frame is either the old colour or the new one
    assert set(after) <= {NAVY, "rgb(255, 255, 255)"}


def test_live_error_still_dims_smoothly(sampled: App) -> None:
    sampled.open()
    settle(sampled, 100)
    before = len(frames(sampled))
    sampled.send(error("NameError", "oops", frames=[], context=[]))
    expect(sampled.page.locator("#error-panel")).to_be_visible()
    settle(sampled)
    opacities = [f["opacity"] for f in frames(sampled)[before:]]
    assert opacities[-1] == pytest.approx(0.45)
    assert any(0.46 < o < 0.99 for o in opacities), opacities


def test_no_transitions_on_load(listening: App) -> None:
    listening.host.snapshot.update(
        DARK_SNAPSHOT, error=error("NameError", "oops", frames=[], context=[])
    )
    listening.open()
    settle(listening)
    assert transitions(listening) == []


def test_no_transitions_on_snapshot_after_reconnect(listening: App) -> None:
    listening.host.snapshot.update(DARK_SNAPSHOT)
    listening.open()
    settle(listening, 100)
    listening.host.snapshot = {**listening.host.snapshot, "background": "#102030", "run": 2}
    listening.host.drop_clients()
    listening.page.wait_for_function("document.body.dataset.run === '2'")
    settle(listening)
    assert transitions(listening) == []


def test_run_resets_background_without_a_transition(listening: App) -> None:
    listening.host.snapshot.update(DARK_SNAPSHOT)
    listening.open()
    settle(listening, 100)
    listening.send(run(2))
    listening.sync()
    settle(listening)
    assert not [t for t in transitions(listening) if t.startswith("background")]
