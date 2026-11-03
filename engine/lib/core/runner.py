"""Child process entry point: run the student's script and report to the supervisor.

Started by the supervisor as ``python -m core.runner <abs script path>``. See ``protocol.md``.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import threading
import tokenize
import traceback
from collections.abc import Callable
from typing import Any, TextIO


def _read_events(stream: TextIO, runtime: Any) -> None:
    """Feed events from the supervisor to the runtime. If the supervisor goes away, exit."""
    while True:
        try:
            line = stream.readline()
        except (OSError, ValueError):
            line = ""
        if not line:
            os._exit(0)
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict):
            with contextlib.suppress(Exception):
                runtime.feed_event(event)


def _execute(script: str, namespace: Callable[[], dict[str, Any]]) -> BaseException | None:
    """Compile and run the script. Returns the uncaught exception, or ``None`` if it finished."""
    try:
        # Compile text, not bytes: Python 3.10 reports SyntaxError columns in bytes for bytes.
        with tokenize.open(script) as handle:
            source = handle.read()
        code = compile(source, script, "exec")
        exec(code, {"__name__": "__main__", "__file__": script, **namespace()})
    except (SystemExit, KeyboardInterrupt):
        return None
    except BaseException as exc:
        return exc
    return None


def main(argv: list[str] | None = None) -> int:
    """Run one script. Returns the process exit code (0 finished, 1 error, 2 bad usage)."""
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        sys.__stderr__.write("usage: python -m core.runner <script.py>\n")  # type: ignore[union-attr]
        return 2
    script = os.path.abspath(args[0])
    script_dir = os.path.dirname(script)

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
    sys.stdin = io.StringIO("")
    threading.Thread(target=_read_events, args=(events_in, runtime), daemon=True).start()

    send({"t": "hello"})
    if sys.path[:1] != [script_dir]:
        sys.path.insert(0, script_dir)
    sys.argv = [script]

    error = _execute(script, namespace)
    payload = build_error_payload(error, script_dir) if error is not None else None
    with contextlib.suppress(Exception):
        runtime.stop()
    send(payload if payload is not None else {"t": "end"})
    return 1 if payload is not None else 0


if __name__ == "__main__":
    try:
        code = main()
    except BaseException:
        traceback.print_exc(file=sys.__stderr__)
        code = 1
    os._exit(code)
