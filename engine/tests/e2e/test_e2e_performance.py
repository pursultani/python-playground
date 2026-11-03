"""Sanity checks that busy programs stay smooth and cannot freeze the page or the supervisor."""

from __future__ import annotations

import time

from e2e_helpers import Playground
from playwright.sync_api import expect

COUNT_MESSAGES = """
(() => {
  const Original = window.EventSource;
  window.__msgs = {};
  window.__ops = 0;
  window.__maxOpsPerFrame = 0;
  window.EventSource = class extends Original {
    constructor(...args) {
      super(...args);
      this.addEventListener("message", (e) => {
        const m = JSON.parse(e.data);
        window.__msgs[m.t] = (window.__msgs[m.t] || 0) + 1;
        if (m.t === "frame") {
          window.__ops += m.ops.length;
          window.__maxOpsPerFrame = Math.max(window.__maxOpsPerFrame, m.ops.length);
        }
      });
    }
  };
})();
"""

LAG_SAMPLER = """
() => {
  window.__lags = [];
  const T0 = window.__t0;
  const tick = () => {
    const node = window.__playground.nodes.get(1);
    if (node && window.__playground.state === 'running') {
      window.__lags.push((Date.now() / 1000 - T0) * 100 - node.props.x);
    }
    requestAnimationFrame(tick);
  };
  tick();
}
"""


def test_200_shapes_moving_every_20ms_stay_smooth(pg: Playground):
    t0 = time.time()
    pg.start(
        f"import time\n"
        f"T0 = {t0!r}\n"
        "shapes = [Circle(i * 3 - 300, (i % 10) * 20 - 100, radius=8) for i in range(200)]\n"
        "start = time.time()\n"
        "while time.time() - start < 3:\n"
        "    stamp = (time.time() - T0) * 100\n"
        "    for i, s in enumerate(shapes):\n"
        "        s.x = stamp + i * 0.01\n"
        "        s.y = (i % 10) * 20 - 100 + (stamp % 20)\n"
        "    wait(0.02)\n"
        "print('done')\n",
        open_page=False,
    )
    pg.open_page()
    pg.page.add_init_script(COUNT_MESSAGES)
    pg.page.reload()
    pg.page.wait_for_selector("body[data-conn='ok']")
    pg.page.evaluate(f"window.__t0 = {t0!r}")
    pg.page.evaluate(LAG_SAMPLER)
    pg.wait_for_console("done")
    lags = pg.page.evaluate("window.__lags")
    msgs = pg.page.evaluate("window.__msgs")
    pg.shot("200-shapes-end")
    assert pg.shapes().count() == 200
    assert len(lags) > 20, "the page must have kept rendering while the program ran"
    # lag in seconds between what Python had set and what the page shows (x is stamp = 100/s)
    lags_s = [lag / 100 for lag in lags]
    third = len(lags_s) // 3
    early = sorted(lags_s[:third])[third // 2]
    late = sorted(lags_s[-third:])[third // 2]
    assert max(lags_s) < 0.5, f"worst lag {max(lags_s):.3f}s"
    assert late < early + 0.15, f"lag is growing: early {early:.3f}s, late {late:.3f}s"
    print(f"200 shapes: lag early {early:.3f}s late {late:.3f}s max {max(lags_s):.3f}s, {msgs}")
    assert msgs.get("frame", 0) < 3 * 70, f"too many frames: {msgs}"
    assert pg.sup.state == "finished"


def test_a_tight_loop_without_wait_is_coalesced_to_about_60_frames_a_second(pg: Playground):
    pg.start("pass\n", open_page=False)
    pg.open_page()
    pg.page.add_init_script(COUNT_MESSAGES)
    pg.page.reload()
    pg.page.wait_for_selector("body[data-conn='ok']")
    pg.edit(
        "import time\n"
        "ball = Circle(0, 0, radius=20)\n"
        "start = time.time()\n"
        "n = 0\n"
        "while time.time() - start < 1.5:\n"
        "    n += 1\n"
        "    ball.x = n % 300\n"
        "print('loops', n > 1000)\n",
        "finished",
    )
    pg.wait_for_console("loops True")
    msgs = pg.page.evaluate("window.__msgs")
    print("tight loop frames in 1.5s:", msgs.get("frame"))
    assert 10 < msgs.get("frame", 0) < 1.5 * 75 + 10, msgs
    assert pg.page.evaluate("window.__maxOpsPerFrame") <= 2


def test_an_endless_print_loop_does_not_freeze_the_page_or_the_supervisor(pg: Playground):
    pg.start("Circle()\nn = 0\nwhile True:\n    n += 1\n    print('line', n, 'x' * 40)\n")
    pg.wait_for_console("line 1")
    for _ in range(5):
        started = time.monotonic()
        assert pg.page.evaluate("1 + 1") == 2
        assert time.monotonic() - started < 1.0, "the page is not responding"
        pg.page.wait_for_timeout(300)
    assert pg.page.locator("#console > span").count() <= 2000
    started = time.monotonic()
    response = pg.page.request.get(pg.sup.url)
    assert response.status == 200
    assert time.monotonic() - started < 1.0, "the supervisor is not responding"
    pg.shot("print-flood")
    started = time.monotonic()
    pg.edit("print('calm')\n", "finished")
    assert time.monotonic() - started < 4
    pg.wait_for_console("calm")
    assert pg.console() == "calm\n"


def test_console_keeps_only_the_last_chunks(pg: Playground):
    pg.start("for i in range(3000):\n    print('row', i)\n    wait(0.001)\nprint('last')\n")
    pg.wait_state("finished", timeout=30000)
    pg.wait_for_console("last")
    assert pg.page.locator("#console > span").count() <= 2000
    assert "row 2999" in pg.console()
    expect(pg.page.locator("#console-count")).not_to_have_text("0")


def test_many_shapes_created_at_once(pg: Playground):
    pg.start(
        "for i in range(1000):\n"
        "    Circle(i % 40 * 20 - 390, i // 40 * 20 - 250, radius=8, title=str(i))\n"
    )
    pg.wait_state("finished")
    expect(pg.shapes()).to_have_count(1000)
    pg.shot("1000-shapes")


def test_wait_with_no_argument_in_a_loop_does_not_flood_or_disconnect(pg: Playground):
    pg.start("pass\n", open_page=False)
    pg.open_page()
    pg.page.add_init_script(COUNT_MESSAGES)
    pg.page.reload()
    pg.page.wait_for_selector("body[data-conn='ok']")
    pg.edit(
        "ball = Circle(-300, 0, radius=20)\nwhile True:\n    ball.x += 0.5\n    wait()\n", "running"
    )
    pg.page.wait_for_timeout(2000)
    msgs = pg.page.evaluate("window.__msgs")
    print("wait() loop messages in 2s:", msgs)
    assert msgs.get("snapshot", 0) == 1, "the page must not have been disconnected and reloaded"
    assert pg.page.locator("body").get_attribute("data-conn") == "ok"
    assert msgs.get("frame", 0) < 2 * 150
    assert pg.sup.client_count == 1
    assert pg.centre(1)[0] > pg.to_screen(-300, 0)[0]
