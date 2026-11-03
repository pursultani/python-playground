"""Child process entry point: run the student's script and report to the supervisor.

Started by the supervisor as ``python -c <boot> <abs script path>`` (the boot code removes the
script's folder from ``sys.path`` before importing ``core``). See ``protocol.md``.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import signal
import sys
import threading
import tokenize
import traceback
from collections.abc import Callable
from typing import Any, TextIO

NO_INPUT_MESSAGE = (
    "input() does not work in Python Playground. "
    "Use on_click or on_key to get answers from the player."
)
EARLY_IMPORTS = ("difflib", "inspect", "json", "linecache", "queue", "threading", "tokenize")


class _NoInput(io.TextIOBase):
    """``sys.stdin`` for students: reading from it explains why that cannot work."""

    def readable(self) -> bool:
        return True

    def read(self, size: int | None = -1) -> str:
        raise EOFError(NO_INPUT_MESSAGE)

    def readline(self, size: int | None = -1) -> str:
        raise EOFError(NO_INPUT_MESSAGE)

    def readlines(self, hint: int = -1) -> list[str]:
        raise EOFError(NO_INPUT_MESSAGE)

    def __next__(self) -> str:
        raise EOFError(NO_INPUT_MESSAGE)


class _ScriptProblem(Exception):
    """The script file itself cannot be used. The message is already friendly."""


def _stop_with_children() -> None:
    """Exit now, taking along programs the script started (when this process leads a group)."""
    if os.name != "nt":
        with contextlib.suppress(OSError):
            if os.getpgrp() == os.getpid():
                os.killpg(os.getpid(), signal.SIGKILL)
    os._exit(0)


def _read_events(stream: TextIO, runtime: Any) -> None:
    """Feed events from the supervisor to the runtime. If the supervisor goes away, exit."""
    while True:
        try:
            line = stream.readline()
        except (OSError, ValueError):
            line = ""
        if not line:
            _stop_with_children()
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict):
            with contextlib.suppress(Exception):
                runtime.feed_event(event)


def _read_source(script: str) -> str:
    name = os.path.basename(script)
    try:
        # Compile text, not bytes: Python 3.10 reports SyntaxError columns in bytes for bytes.
        with tokenize.open(script) as handle:
            source = handle.read()
    except FileNotFoundError:
        raise _ScriptProblem(
            f"I can't find {name}. Check that the file is still in its folder."
        ) from None
    except (UnicodeDecodeError, SyntaxError, LookupError):
        raise _ScriptProblem(
            f"{name} isn't saved as UTF-8. Save the file again as UTF-8."
        ) from None
    except OSError:
        raise _ScriptProblem(
            f"I can't read {name}. Check that you are allowed to open it."
        ) from None
    if "\x00" in source:
        raise _ScriptProblem(
            f"{name} has a null byte in it, so Python can't read it. "
            "Save the file again as a plain text file in UTF-8."
        )
    return source


def _execute(script: str, namespace: Callable[[], dict[str, Any]]) -> BaseException | None:
    """Compile and run the script. Returns the uncaught exception, or ``None`` if it finished."""
    try:
        code = compile(_read_source(script), script, "exec")
        exec(code, {"__name__": "__main__", "__file__": script, **namespace()})
    except (SystemExit, KeyboardInterrupt):
        return None
    except BaseException as exc:
        return exc
    return None


def run() -> None:
    """Run ``main()`` and exit the process (the entry point used by the supervisor)."""
    try:
        code = main()
    except BaseException:
        traceback.print_exc(file=sys.__stderr__)
        code = 1
    os._exit(code)


def main(argv: list[str] | None = None) -> int:
    """Run one script. Returns the process exit code (0 finished, 1 error, 2 bad usage)."""
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        sys.__stderr__.write("usage: python -m core.runner <script.py>\n")  # type: ignore[union-attr]
        return 2
    script = os.path.abspath(args[0])
    script_dir = os.path.dirname(script)

    for name in EARLY_IMPORTS:
        with contextlib.suppress(ImportError):
            __import__(name)
    from core import namespace
    from core._errors import build_error_payload
    from core._protocol import JsonLineWriter
    from core._runtime import Runtime

    events_in = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="replace", newline="\n")
    protocol_fd = os.dup(1)
    os.dup2(2, 1)
    writer = JsonLineWriter(
        open(protocol_fd, "w", encoding="utf-8", errors="replace", newline="\n")  # noqa: SIM115
    )

    def send(message: dict[str, Any]) -> None:
        try:
            writer.write(message)
        except (OSError, ValueError):
            os._exit(0)

    runtime = Runtime(send)
    runtime.start()
    sys.stdout = runtime.print_stream("stdout")
    sys.stderr = runtime.print_stream("stderr")
    sys.stdin = _NoInput()
    threading.Thread(target=_read_events, args=(events_in, runtime), daemon=True).start()

    send({"t": "hello"})
    if script_dir not in sys.path:
        sys.path.append(script_dir)
    sys.argv = [script]

    error = _execute(script, namespace)
    payload = None
    if isinstance(error, _ScriptProblem):
        payload = {
            "t": "error",
            "kind": "Error",
            "message": str(error),
            "frames": [],
            "context": [],
        }
    elif error is not None:
        payload = build_error_payload(error, script_dir)
    with contextlib.suppress(Exception):
        runtime.stop()
    send(payload if payload is not None else {"t": "end"})
    return 1 if payload is not None else 0


if __name__ == "__main__":
    run()
