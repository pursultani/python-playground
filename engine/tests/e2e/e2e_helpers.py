"""A real supervisor + real page + real child process, wrapped for readable tests."""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any

from core.supervisor import Supervisor
from playwright.sync_api import Browser, BrowserContext, Locator, Page, ViewportSize, expect

SHOTS = Path(
    os.environ.get(
        "PLAYGROUND_SHOTS",
        "/private/var/folders/mm/y6zzp5q160n30k0hz12tgp7m0000gn/T/opencode/pp-e2e",
    )
)
TIMEOUT_MS = 10_000


class Playground:
    """One student script, one supervisor on a random port, one browser page."""

    def __init__(self, directory: Path, browser: Browser, test_name: str) -> None:
        self.directory = directory
        self.browser = browser
        self.test_name = re.sub(r"\W+", "-", test_name).strip("-")
        self.script = directory / "main.py"
        self.supervisor: Supervisor | None = None
        self.context: BrowserContext | None = None
        self.page: Page
        self.js_errors: list[str] = []
        self.console_errors: list[str] = []
        self.logs: list[str] = []
        self.pages: list[Page] = []
        SHOTS.mkdir(parents=True, exist_ok=True)

    def start(
        self,
        source: str | bytes,
        *,
        open_page: bool = True,
        viewport: ViewportSize | None = None,
        poll_interval: float = 0.05,
        port: int = 0,
    ) -> Playground:
        if isinstance(source, bytes):
            self.script.write_bytes(source)
        else:
            self.script.write_text(source, encoding="utf-8")
        self.supervisor = Supervisor(
            self.script, port=port, poll_interval=poll_interval, log=self.logs.append
        )
        self.supervisor.start()
        if open_page:
            self.open_page(viewport)
        return self

    def open_page(self, viewport: ViewportSize | None = None) -> Page:
        assert self.supervisor is not None
        self.context = self.browser.new_context(
            viewport=viewport or ViewportSize(width=1100, height=900)
        )
        page = self.new_page()
        page.goto(self.supervisor.url)
        page.wait_for_selector("body[data-conn='ok']", timeout=TIMEOUT_MS)
        return page

    def new_page(self) -> Page:
        assert self.context is not None
        page = self.context.new_page()
        page.set_default_timeout(TIMEOUT_MS)
        page.on("pageerror", lambda exc: self.js_errors.append(str(exc)))
        page.on("console", self._on_console)
        self.page = page
        self.pages.append(page)
        return page

    def _on_console(self, message: Any) -> None:
        if message.type == "error" and "Failed to load resource" not in message.text:
            self.console_errors.append(message.text)

    def close(self) -> None:
        if self.context is not None:
            self.context.close()
        if self.supervisor is not None:
            self.supervisor.stop()

    @property
    def sup(self) -> Supervisor:
        assert self.supervisor is not None
        return self.supervisor

    def body(self) -> Locator:
        return self.page.locator("body")

    def edit(self, source: str, expect_state: str | None = None) -> int:
        """Rewrite the script like an editor would; wait until the new run reaches the page."""
        before = self.sup.run
        previous = self.script.stat().st_mtime_ns
        self.script.write_text(source, encoding="utf-8")
        stat = self.script.stat()
        if stat.st_mtime_ns <= previous:
            os.utime(self.script, ns=(stat.st_atime_ns, previous + 10_000_000))
        run = before + 1
        expect(self.body()).to_have_attribute("data-run", str(run), timeout=TIMEOUT_MS)
        if expect_state:
            self.wait_state(expect_state)
        return run

    def wait_state(self, state: str, timeout: int = TIMEOUT_MS) -> None:
        expect(self.body()).to_have_attribute("data-state", state, timeout=timeout)

    def wait_for_console(self, text: str, timeout: int = TIMEOUT_MS) -> None:
        expect(self.page.locator("#console")).to_contain_text(text, timeout=timeout)

    def console(self) -> str:
        return self.page.locator("#console").inner_text()

    def pid(self) -> int:
        """The child's process id, for scripts that start with ``print(os.getpid())``."""
        found: list[int] = []

        def printed() -> bool:
            words = self.console().split()
            if words and words[0].isdigit():
                found[:] = [int(words[0])]
            return bool(found)

        poll(printed, 10, "the program to print its pid")
        return found[0]

    def shape(self, id: int) -> Locator:
        return self.page.locator(f"#shapes > g[data-id='{id}'], #guides > g[data-id='{id}']")

    def shapes(self) -> Locator:
        return self.page.locator("#shapes > g")

    def ids(self) -> list[int]:
        return self.page.evaluate("[...window.__playground.nodes.keys()].sort((a, b) => a - b)")

    def tag(self, id: int, name: str = "mark") -> None:
        """Remember a DOM node so ``is_same_node`` can tell whether it was replaced."""
        self.page.evaluate(
            "([id, name]) => { window.__tags = window.__tags || {};"
            " window.__tags[name] = window.__playground.nodes.get(id).el; }",
            [id, name],
        )

    def is_same_node(self, id: int, name: str = "mark") -> bool:
        return self.page.evaluate(
            "([id, name]) => window.__tags[name] === window.__playground.nodes.get(id)?.el",
            [id, name],
        )

    def transform(self, id: int) -> str:
        return self.shape(id).evaluate("e => getComputedStyle(e).transform")

    def centre(self, id: int) -> tuple[float, float]:
        box = self.shape(id).bounding_box()
        assert box is not None
        return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2

    def canvas_box(self) -> dict[str, float]:
        """The 800x600 area inside the SVG (the SVG letterboxes, so compute it)."""
        return self.page.evaluate(
            """() => {
              const m = document.getElementById('canvas').getScreenCTM();
              return {x: m.e - 400 * m.a, y: m.f - 300 * m.d, width: 800 * m.a, height: 600 * m.d};
            }"""
        )

    def to_screen(self, x: float, y: float) -> tuple[float, float]:
        box = self.canvas_box()
        scale = box["width"] / 800
        return box["x"] + (x + 400) * scale, box["y"] + (300 - y) * scale

    def click_at(self, x: float, y: float) -> None:
        sx, sy = self.to_screen(x, y)
        self.page.mouse.click(sx, sy)

    def press(self, key: str) -> None:
        self.page.keyboard.press(key)

    def shot(self, name: str) -> Path:
        path = SHOTS / f"{self.test_name}--{name}.png"
        self.page.screenshot(path=str(path))
        return path

    def error_text(self) -> str:
        return self.page.locator("#error-panel").inner_text()

    def pixel(self, x: float, y: float) -> tuple[int, int, int]:
        """The colour of a screen pixel, read from a screenshot clip."""
        png = self.page.screenshot(clip={"x": x, "y": y, "width": 1, "height": 1})
        return _decode_pixel(png)

    def expect_dimmed(self, dimmed: bool = True) -> None:
        """Wait for the canvas to be dimmed (an error is showing) or back to normal."""
        test = "< 0.5" if dimmed else "== 1"
        self.page.wait_for_function(
            "() => Number(getComputedStyle(document.getElementById('canvas-wrap')).opacity) " + test
        )

    def settle(self, ms: int = 250) -> None:
        """Let CSS transitions finish."""
        self.page.wait_for_timeout(ms)


def _decode_pixel(png: bytes) -> tuple[int, int, int]:
    import struct
    import zlib

    pos = 8
    width = height = 0
    data = b""
    while pos < len(png):
        (length,) = struct.unpack(">I", png[pos : pos + 4])
        kind = png[pos + 4 : pos + 8]
        chunk = png[pos + 8 : pos + 8 + length]
        if kind == b"IHDR":
            width, height = struct.unpack(">II", chunk[:8])
        elif kind == b"IDAT":
            data += chunk
        pos += 12 + length
    raw = zlib.decompress(data)
    assert width == 1 and height == 1
    return raw[1], raw[2], raw[3]


def poll(condition: Any, timeout: float = 10.0, what: str = "condition") -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError(f"timed out waiting for {what}")
        time.sleep(0.02)
