"""The real student path: ./run.sh main.py in a terminal, a browser tab, Ctrl+C."""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import threading
import time
from pathlib import Path

from e2e_helpers import TIMEOUT_MS, poll
from playwright.sync_api import Browser, expect

ROOT = Path(__file__).resolve().parents[3]


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class Terminal:
    def __init__(self, script: Path, port: int) -> None:
        env = {k: v for k, v in os.environ.items() if k not in ("VIRTUAL_ENV", "PYTHONPATH")}
        self.process = subprocess.Popen(
            [str(ROOT / "run.sh"), str(script), "--no-browser", "--port", str(port)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=script.parent,
            env=env,
        )
        self.lines: list[str] = []
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self) -> None:
        assert self.process.stdout is not None
        for line in self.process.stdout:
            self.lines.append(line.rstrip("\n"))

    def wait_for(self, text: str, timeout: float = 15) -> str:
        found: list[str] = []

        def seen() -> bool:
            found[:] = [line for line in self.lines if text in line]
            return bool(found)

        poll(seen, timeout, f"terminal line containing {text!r}; saw {self.lines}")
        return found[0]

    def interrupt(self) -> int:
        self.process.send_signal(signal.SIGINT)
        return self.process.wait(timeout=10)

    def kill(self) -> None:
        if self.process.poll() is None:
            self.process.kill()
            self.process.wait()


def test_run_sh_serves_the_page_restarts_on_save_and_stops_on_ctrl_c(
    chromium: Browser, tmp_path: Path
):
    script = tmp_path / "main.py"
    script.write_text("print('hello from run.sh')\nCircle(100, 100, color='red')\n")
    port = free_port()
    terminal = Terminal(script, port)
    context = chromium.new_context(viewport={"width": 1100, "height": 900})
    errors: list[str] = []
    try:
        banner = terminal.wait_for("Python Playground running at")
        assert f"http://127.0.0.1:{port}" in banner
        terminal.wait_for("Watching main.py")
        page = context.new_page()
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.goto(f"http://127.0.0.1:{port}/")
        expect(page.locator("body")).to_have_attribute("data-state", "finished", timeout=TIMEOUT_MS)
        expect(page.locator("#console")).to_have_text("hello from run.sh\n")
        expect(page.locator("#shapes > g")).to_have_count(1)
        terminal.wait_for("Program finished")

        script.write_text("print('second')\nboom\n")
        terminal.wait_for("main.py changed - restarting")
        expect(page.locator("body")).to_have_attribute("data-state", "crashed", timeout=TIMEOUT_MS)
        line = terminal.wait_for("Program stopped by an error")
        assert "NameError" in line and "main.py, line 2" in line
        # print output belongs in the browser, not the terminal
        assert not any("second" in captured for captured in terminal.lines)

        script.write_text("while True:\n    wait(0.1)\n")
        expect(page.locator("body")).to_have_attribute("data-state", "running", timeout=TIMEOUT_MS)
        started = time.monotonic()
        assert terminal.interrupt() == 0
        assert time.monotonic() - started < 5
        output = "\n".join(terminal.lines)
        assert "Traceback" not in output
        with socket.socket() as probe:
            probe.settimeout(1)
            assert probe.connect_ex(("127.0.0.1", port)) != 0
        assert errors == []
    finally:
        context.close()
        terminal.kill()


def test_run_sh_reports_a_busy_port_in_plain_english(tmp_path: Path):
    script = tmp_path / "main.py"
    script.write_text("pass\n")
    with socket.socket() as blocker:
        blocker.bind(("127.0.0.1", 0))
        blocker.listen()
        busy = blocker.getsockname()[1]
        terminal = Terminal(script, busy)
        try:
            assert terminal.process.wait(timeout=15) == 1
        finally:
            terminal.kill()
        joined = " ".join(terminal.lines)
        assert "already in use" in joined and "--port" in joined
        assert "Traceback" not in joined
