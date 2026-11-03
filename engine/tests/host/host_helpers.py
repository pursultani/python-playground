"""Shared helpers for the host tests: SSE client, HTTP calls, supervisor factory."""

from __future__ import annotations

import http.client
import json
import os
import socket
import sys
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from core.supervisor import Supervisor

HERE = Path(__file__).resolve().parent
FAKE_CHILD = str(HERE / "fake_child.py")


def fake_argv(script: str) -> list[str]:
    return [sys.executable, "-u", FAKE_CHILD, script]


class SSEClient:
    """A bare-bones Server-Sent Events reader over ``http.client``."""

    def __init__(self, port: int, timeout: float = 5.0) -> None:
        self.conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
        self.conn.request("GET", "/events")
        self.response = self.conn.getresponse()
        self.comments: list[str] = []

    def next_message(self) -> dict[str, Any]:
        """Return the next JSON message. Raises ``EOFError`` if the server closed the stream."""
        message = self.try_next()
        if message is None:
            raise EOFError("the event stream ended")
        return message

    def try_next(self) -> dict[str, Any] | None:
        """Like ``next_message`` but returns ``None`` when the server closes the stream."""
        data: list[str] = []
        while True:
            raw = self.response.readline()
            if not raw:
                return None
            line = raw.decode("utf-8").rstrip("\r\n")
            if line.startswith(":"):
                self.comments.append(line)
            elif line.startswith("data: "):
                data.append(line[6:])
            elif line == "" and data:
                return json.loads("\n".join(data))

    def read_until(self, predicate: Callable[[dict[str, Any]], bool]) -> list[dict[str, Any]]:
        """Collect messages up to and including the first one that satisfies ``predicate``."""
        seen: list[dict[str, Any]] = []
        while True:
            message = self.try_next()
            if message is None:
                raise AssertionError(f"stream ended before the expected message; saw {seen}")
            seen.append(message)
            if predicate(message):
                return seen

    def close(self) -> None:
        self.response.close()
        self.conn.close()


def request(
    port: int,
    method: str,
    path: str,
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
    host: str | None = None,
) -> tuple[int, dict[str, str], bytes]:
    """Make one request with a raw path (no normalisation) and return status, headers, body."""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.putrequest(method, path, skip_host=host is not None)
        if host is not None:
            conn.putheader("Host", host)
        for name, value in (headers or {}).items():
            conn.putheader(name, value)
        conn.putheader("Content-Length", str(len(body or b"")))
        conn.endheaders(body)
        response = conn.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        conn.close()


def post_event(port: int, event: Any) -> int:
    return request(port, "POST", "/event", json.dumps(event).encode())[0]


def wait_until(
    condition: Callable[[], bool], timeout: float = 5.0, what: str = "condition"
) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError(f"timed out waiting for {what}")
        time.sleep(0.02)


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def console_text(supervisor: Supervisor) -> str:
    return "".join(chunk["text"] for chunk in supervisor.snapshot()["console"])


def write_script(directory: Path, source: str, name: str = "main.py") -> Path:
    path = directory / name
    path.write_text(source, encoding="utf-8")
    return path


def bump_mtime(path: Path, seconds: float = 5.0) -> None:
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + int(seconds * 1e9)))


@contextmanager
def running(supervisor: Supervisor) -> Iterator[Supervisor]:
    supervisor.start()
    try:
        yield supervisor
    finally:
        supervisor.stop()


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]
