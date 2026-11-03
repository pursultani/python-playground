"""Helpers for driving the page: message builders and a small wrapper around a Playwright page."""

from __future__ import annotations

from typing import Any

from fake_host import FakeHost
from playwright.sync_api import Locator, Page, expect

TIMEOUT_MS = 5000

# Lets tests know when the page has handled a "noop" message (see App.sync).
WATCH_SSE = """
(() => {
  const Original = window.EventSource;
  window.EventSource = class extends Original {
    constructor(...args) {
      super(...args);
      this.addEventListener("message", (e) => {
        const m = JSON.parse(e.data);
        if (m.t === "noop") setTimeout(() => { window.__noop = m.n; }, 0);
      });
    }
  };
})();
"""


def create(id: int, type: str, **props: Any) -> dict[str, Any]:
    return {"op": "create", "id": id, "type": type, "props": props}


def update(id: int, **props: Any) -> dict[str, Any]:
    return {"op": "update", "id": id, "props": props}


def remove(id: int) -> dict[str, Any]:
    return {"op": "remove", "id": id}


def frame(*ops: dict[str, Any]) -> dict[str, Any]:
    return {"t": "frame", "ops": list(ops)}


def run(n: int) -> dict[str, Any]:
    return {"t": "run", "run": n}


def status(state: str, run_number: int = 1) -> dict[str, Any]:
    return {"t": "status", "run": run_number, "state": state}


def print_(text: str, stream: str = "stdout") -> dict[str, Any]:
    return {"t": "print", "text": text, "stream": stream}


def error(
    kind: str = "NameError",
    message: str = "name 'bal' is not defined. Did you mean: 'ball'?",
    frames: list[dict[str, Any]] | None = None,
    context: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "t": "error",
        "kind": kind,
        "message": message,
        "frames": frames if frames is not None else [],
        "context": context if context is not None else [],
    }


class App:
    """A page connected to a fake host."""

    def __init__(self, host: FakeHost, page: Page) -> None:
        self.host = host
        self.page = page
        self.js_errors: list[str] = []
        self._syncs = 0
        page.add_init_script(WATCH_SSE)
        page.on("pageerror", lambda exc: self.js_errors.append(str(exc)))

    def open(self) -> App:
        self.page.goto(self.host.url)
        self.page.wait_for_selector("body[data-conn='ok']", timeout=TIMEOUT_MS)
        self.sync()
        return self

    def send(self, *messages: dict[str, Any]) -> None:
        self.host.push(*messages)

    def sync(self) -> None:
        """Wait until every message sent so far has been handled by the page."""
        self._syncs += 1
        self.host.push({"t": "noop", "n": self._syncs})
        self.page.wait_for_function("n => window.__noop === n", arg=self._syncs, timeout=TIMEOUT_MS)

    def shape(self, id: int) -> Locator:
        return self.page.locator(f"#shapes > g[data-id='{id}'], #guides > g[data-id='{id}']")

    def shapes(self) -> Locator:
        return self.page.locator("#shapes > g")

    def expect_state(self, state: str) -> None:
        expect(self.page.locator("body")).to_have_attribute("data-state", state, timeout=TIMEOUT_MS)

    def console_text(self) -> str:
        return self.page.locator("#console").inner_text()

    def ids(self) -> list[int]:
        return self.page.evaluate("[...window.__playground.nodes.keys()].sort((a, b) => a - b)")
