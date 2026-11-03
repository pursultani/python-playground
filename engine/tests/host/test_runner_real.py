"""Runs ``core.runner`` against the real runtime (WP-A). Skipped until that exists."""

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

pytest.importorskip("core._runtime")
core = pytest.importorskip("core")
if not hasattr(core, "namespace"):
    pytest.skip("core.namespace() is not available yet", allow_module_level=True)

from host_helpers import pid_alive, wait_until  # noqa: E402

LIB = str(Path(core.__file__).resolve().parent.parent)


class Child:
    """The runner as a subprocess, with its protocol messages collected on a thread."""

    def __init__(self, directory: Path, source: str, name: str = "main.py") -> None:
        self.directory = directory
        self.script = directory / name
        self.script.write_text(source, encoding="utf-8")
        env = dict(os.environ, PYTHONPATH=LIB, PYTHONDONTWRITEBYTECODE="1")
        self.process = subprocess.Popen(
            [sys.executable, "-u", "-m", "core.runner", str(self.script)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=directory,
            env=env,
        )
        self.messages: list[dict] = []
        self.raw_lines: list[bytes] = []
        self._reader = threading.Thread(target=self._read, daemon=True)
        self._reader.start()

    def _read(self) -> None:
        assert self.process.stdout is not None
        for raw in self.process.stdout:
            self.raw_lines.append(raw)
            self.messages.append(json.loads(raw))

    def send(self, event: dict) -> None:
        assert self.process.stdin is not None
        self.process.stdin.write((json.dumps(event) + "\n").encode())
        self.process.stdin.flush()

    def wait(self, timeout: float = 10.0) -> int:
        code = self.process.wait(timeout)
        self._reader.join(timeout)
        return code

    def kinds(self) -> list[str]:
        return [m["t"] for m in self.messages]

    def console(self, stream: str | None = None) -> str:
        return "".join(
            m["text"] for m in self.messages if m["t"] == "print" and stream in (None, m["stream"])
        )

    def stderr(self) -> str:
        assert self.process.stderr is not None
        return self.process.stderr.read().decode()

    def close(self) -> None:
        if self.process.poll() is None:
            self.process.kill()
        self.process.wait()
        for pipe in (self.process.stdin, self.process.stdout, self.process.stderr):
            if pipe:
                pipe.close()


@pytest.fixture
def child(tmp_path):
    made: list[Child] = []

    def start(source: str, name: str = "main.py") -> Child:
        instance = Child(tmp_path, source, name)
        made.append(instance)
        return instance

    yield start
    for instance in made:
        instance.close()


def test_normal_run_sends_hello_frames_and_end(child):
    run = child("c = Circle(x=10, color='red')\nprint('hello')\nc.x = 20\n")
    assert run.wait() == 0
    assert run.kinds()[0] == "hello"
    assert run.kinds()[-1] == "end"
    frames = [m for m in run.messages if m["t"] == "frame"]
    ops = [op for frame in frames for op in frame["ops"]]
    assert ops[0]["op"] == "create" and ops[0]["type"] == "circle"
    assert ops[0]["props"]["color"] == "red"
    assert run.console("stdout") == "hello\n"


def test_the_api_is_preloaded_without_imports(child):
    run = child(
        "print(__name__, Path.__name__ if 'Path' in globals() else 'no-path')\nRectangle()\n"
    )
    assert run.wait() == 0
    assert run.console() == "__main__ no-path\n"


def test_dunder_file_is_the_absolute_script_path(child):
    run = child("print(__file__)\n")
    run.wait()
    assert run.console().strip() == str(run.script)


def test_stderr_goes_to_the_console_as_stderr(child):
    run = child("import sys\nprint('out')\nprint('err', file=sys.stderr)\n")
    assert run.wait() == 0
    assert run.console("stdout") == "out\n"
    assert run.console("stderr") == "err\n"


def test_prints_are_flushed_before_the_error(child):
    run = child("print('before')\nCircle()\nundefined_name\n")
    assert run.wait() == 1
    kinds = run.kinds()
    assert kinds[-1] == "error"
    assert kinds.index("print") < kinds.index("error")
    assert "frame" in kinds[: kinds.index("error")]
    error = run.messages[-1]
    assert error["kind"] == "NameError"
    assert error["frames"][-1]["line"] == 3
    assert "end" not in kinds


def test_syntax_error(child):
    run = child("print('ok'\n")
    assert run.wait() == 1
    error = run.messages[-1]
    assert run.kinds()[0] == "hello"
    assert error["t"] == "error" and error["kind"] == "SyntaxError"
    assert error["frames"][0]["file"] == "main.py"


def test_exit_and_sys_exit_count_as_finished(child):
    for source in ("print('a')\nexit()\nprint('b')\n", "import sys\nprint('a')\nsys.exit(3)\n"):
        run = child(source)
        assert run.wait() == 0
        assert run.kinds()[-1] == "end"
        assert run.console() == "a\n"


def test_missing_script_is_reported_as_an_error(tmp_path):
    process = subprocess.Popen(
        [sys.executable, "-m", "core.runner", str(tmp_path / "gone.py")],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        env=dict(os.environ, PYTHONPATH=LIB),
        cwd=tmp_path,
    )
    try:
        assert process.stdout is not None
        messages = [json.loads(process.stdout.readline()) for _ in range(2)]
        assert process.wait(timeout=10) == 1
    finally:
        process.kill()
    assert messages[-1]["t"] == "error" and messages[-1]["kind"] == "FileNotFoundError"


def test_stray_writes_to_fd_1_do_not_corrupt_the_protocol(child):
    run = child("import os\nos.write(1, b'junk from C land\\n')\nprint('fine')\n")
    assert run.wait() == 0
    assert run.console() == "fine\n"
    assert all(line.startswith(b"{") for line in run.raw_lines)
    assert "junk from C land" in run.stderr()


def test_input_is_not_supported_and_raises_eof_error(child):
    run = child("input('name? ')\n")
    assert run.wait() == 1
    assert run.messages[-1]["kind"] == "EOFError"


def test_script_directory_is_importable_and_module_errors_show_relative_names(child, tmp_path):
    (tmp_path / "helpers.py").write_text("def boom():\n    raise ValueError('inside helper')\n")
    run = child("import helpers\nhelpers.boom()\n")
    assert run.wait() == 1
    error = run.messages[-1]
    assert [f["file"] for f in error["frames"]] == ["main.py", "helpers.py"]
    assert error["message"] == "inside helper"


def test_events_reach_handlers_inside_wait(child):
    source = (
        "def clicked(x, y):\n"
        "    print('click', x, y)\n"
        "def pressed(key):\n"
        "    print('key', key)\n"
        "    if key == 'q':\n"
        "        exit()\n"
        "on_click(clicked)\n"
        "on_key(pressed)\n"
        "while True:\n"
        "    wait(0.02)\n"
    )
    run = child(source)
    wait_until(lambda: "hello" in run.kinds(), what="hello")
    run.send({"t": "click", "x": 3, "y": -4, "target": None})
    run.send({"t": "key", "key": "a"})
    run.send({"t": "key", "key": "q"})
    assert run.wait() == 0
    assert run.console() == "click 3 -4\nkey a\nkey q\n"
    assert run.kinds()[-1] == "end"


def test_handler_error_ends_the_program_with_both_frames(child):
    source = (
        "def clicked(x, y):\n    nothing_here\non_click(clicked)\nwhile True:\n    wait(0.02)\n"
    )
    run = child(source)
    wait_until(lambda: "hello" in run.kinds(), what="hello")
    run.send({"t": "click", "x": 0, "y": 0, "target": None})
    assert run.wait() == 1
    error = run.messages[-1]
    assert error["kind"] == "NameError"
    assert [f["function"] for f in error["frames"]] == ["<module>", "clicked"]
    assert [f["line"] for f in error["frames"]] == [5, 2]


def test_malformed_events_are_ignored(child):
    run = child("while True:\n    wait(0.02)\n")
    wait_until(lambda: "hello" in run.kinds(), what="hello")
    assert run.process.stdin is not None
    run.process.stdin.write(b"not json\n[1]\n\n")
    run.process.stdin.flush()
    time.sleep(0.2)
    assert run.process.poll() is None


def test_child_exits_when_the_supervisor_goes_away(child):
    run = child("while True:\n    pass\n")
    wait_until(lambda: "hello" in run.kinds(), what="hello")
    assert run.process.stdin is not None
    run.process.stdin.close()
    started = time.monotonic()
    assert run.wait(5) == 0
    assert time.monotonic() - started < 3
    assert not pid_alive(run.process.pid)


def test_child_exits_after_the_script_even_with_a_stray_thread(child):
    source = "import threading, time\nthreading.Thread(target=lambda: time.sleep(60)).start()\n"
    run = child(source)
    assert run.wait(5) == 0
    assert run.kinds()[-1] == "end"


def test_keyboard_interrupt_means_finished(child):
    run = child("raise KeyboardInterrupt\n")
    assert run.wait() == 0
    assert run.kinds()[-1] == "end"


def test_unicode_output_round_trips(child):
    run = child("print('héllo 😀 世界')\nText('héllo 😀')\n")
    assert run.wait() == 0
    assert run.console() == "héllo 😀 世界\n"


def test_lone_surrogates_do_not_break_the_channel(child):
    run = child("print('a\\ud800b')\nprint('after')\n")
    assert run.wait() == 0
    assert "after" in run.console()
    assert run.kinds()[-1] == "end"


def test_wrong_usage_exits_2():
    result = subprocess.run(
        [sys.executable, "-m", "core.runner"],
        capture_output=True,
        env=dict(os.environ, PYTHONPATH=LIB),
        timeout=10,
        stdin=subprocess.DEVNULL,
    )
    assert result.returncode == 2
