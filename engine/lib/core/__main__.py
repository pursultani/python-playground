"""Command line: ``python -m core <script.py> [--port N] [--no-browser]``."""

from __future__ import annotations

import argparse
import contextlib
import os
import signal
import sys
import threading
from typing import Any

DEFAULT_PORT = 8765
PORT_TRIES = 20
USAGE_HINT = "Try:  python -m core main.py"

_print_lock = threading.Lock()
_held: list[str] | None = None


def _say(text: str) -> None:
    with _print_lock:
        if _held is not None:
            _held.append(text)
            return
        sys.stdout.write(text + "\n")
        sys.stdout.flush()


def _start_printing(first_lines: list[str]) -> None:
    """Print ``first_lines``, then anything logged since startup, then print directly."""
    global _held
    with _print_lock:
        lines, _held = first_lines + (_held or []), None
        for line in lines:
            sys.stdout.write(line + "\n")
        sys.stdout.flush()


def _fail(text: str, code: int) -> int:
    with _print_lock:
        sys.stderr.write(text + "\n")
        sys.stderr.flush()
    return code


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m core",
        description="Run a Python Playground program and show it in your browser.",
    )
    parser.add_argument("script", nargs="?", help="the Python file to run, for example main.py")
    parser.add_argument("--port", type=int, help=f"port to use (default: {DEFAULT_PORT})")
    parser.add_argument(
        "--no-browser", action="store_true", help="do not open the browser automatically"
    )
    return parser


def _check_script(script: str) -> str | None:
    """Return a friendly problem description, or ``None`` if the file is fine."""
    if os.path.isdir(script):
        return f"'{script}' is a folder, not a Python file. {USAGE_HINT}"
    if not os.path.exists(script):
        return f"I can't find the file '{script}'. Check the name and the folder, then try again."
    if not os.access(script, os.R_OK):
        return f"I can't read the file '{script}'. Check that you are allowed to open it."
    return None


def _raise_exit(signum: int, frame: Any) -> None:
    raise SystemExit(0)


def main(argv: list[str] | None = None) -> int:
    """Run the playground. Returns the process exit code."""
    if sys.version_info < (3, 10):  # noqa: UP036
        version = f"{sys.version_info[0]}.{sys.version_info[1]}"
        return _fail(
            f"Python Playground needs Python 3.10 or newer, but this is Python {version}.\n"
            "Please install a newer Python from https://www.python.org/downloads/ and try again.",
            1,
        )

    args = _parser().parse_args(argv)
    if args.script is None:
        return _fail(f"Please tell me which file to run. {USAGE_HINT}", 2)
    problem = _check_script(args.script)
    if problem:
        return _fail(problem, 2)
    if args.port is not None and not 1 <= args.port <= 65535:
        return _fail("The port must be a number between 1 and 65535.", 2)

    from core.supervisor import PortUnavailable, Supervisor

    global _held
    _held = []
    exact = args.port is not None
    port: int = DEFAULT_PORT if args.port is None else args.port
    supervisor = Supervisor(
        args.script,
        port=port,
        open_browser=not args.no_browser,
        port_tries=0 if exact else PORT_TRIES,
        log=_say,
    )
    try:
        supervisor.start()
    except PortUnavailable as exc:
        if exact:
            return _fail(
                f"Port {exc.first} is already in use. "
                "Close the other program, or pick a different port with --port.",
                1,
            )
        return _fail(
            f"I could not find a free port between {exc.first} and {exc.last}. "
            "Close some programs, or pick a port with --port.",
            1,
        )

    with contextlib.suppress(ValueError, OSError):
        signal.signal(signal.SIGTERM, _raise_exit)
    try:
        _start_printing(
            [
                f"Python Playground running at {supervisor.url.rstrip('/')}  (Ctrl+C to stop)",
                f"Watching {supervisor.script.name}",
            ]
        )
        supervisor.wait_until_stopped()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        with contextlib.suppress(KeyboardInterrupt):
            supervisor.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
