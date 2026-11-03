"""A tiny stand-in for the real supervisor, used to test the browser page on its own.

It serves ``core/static``, speaks Server-Sent Events on ``/events`` and records what the page
sends to ``/event`` and ``/restart``. Tests push scripted messages with :meth:`FakeHost.push`.
"""

from __future__ import annotations

import json
import mimetypes
import queue
import threading
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

STATIC_DIR = Path(__file__).resolve().parents[2] / "lib" / "core" / "static"

_CLOSE = object()


def default_snapshot() -> dict[str, Any]:
    return {
        "t": "snapshot",
        "run": 1,
        "state": "running",
        "script": "main.py",
        "background": "white",
        "objects": [],
        "console": [],
        "error": None,
    }


class _Handler(BaseHTTPRequestHandler):
    server: _Server  # type: ignore[assignment]
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: Any) -> None:
        pass

    def _send(self, status: int, body: bytes = b"", content_type: str = "text/plain") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/events":
            self._serve_events()
            return
        name = "index.html" if path == "/" else path.removeprefix("/static/")
        file = (STATIC_DIR / name).resolve()
        if (path != "/" and not path.startswith("/static/")) or STATIC_DIR not in file.parents:
            self._send(404, b"not found")
            return
        if not file.is_file():
            self._send(404, b"not found")
            return
        ctype = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
        self._send(200, file.read_bytes(), ctype)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        host = self.server.host
        if self.path == "/restart":
            host._record("restarts", True)
        elif self.path == "/event":
            try:
                host._record("events", json.loads(raw))
            except ValueError:
                self._send(400, b"bad json")
                return
        else:
            self._send(404, b"not found")
            return
        self._send(204)

    def _serve_events(self) -> None:
        host = self.server.host
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        self.wfile.write(f"retry: {host.retry_ms}\n\n".encode())
        client: queue.Queue[Any] = queue.Queue()
        with host._lock:
            client.put(deepcopy(host.snapshot))
            host._clients.append(client)
            host.connections += 1
        try:
            while not host._stopping.is_set():
                try:
                    item = client.get(timeout=0.2)
                except queue.Empty:
                    continue
                if item is _CLOSE:
                    break
                self.wfile.write(b"data: " + json.dumps(item).encode() + b"\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            with host._lock:
                if client in host._clients:
                    host._clients.remove(client)


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    host: FakeHost


class FakeHost:
    """Serves the page and plays scripted SSE messages. Use as a context manager."""

    def __init__(self) -> None:
        self.snapshot: dict[str, Any] = default_snapshot()
        self.events: list[dict[str, Any]] = []
        self.restarts = 0
        self.connections = 0
        self.retry_ms = 300
        self._clients: list[queue.Queue[Any]] = []
        self._lock = threading.Lock()
        self._stopping = threading.Event()
        self._server = _Server(("127.0.0.1", 0), _Handler)
        self._server.host = self
        self._thread = threading.Thread(
            target=self._server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True
        )

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}/"

    def start(self) -> FakeHost:
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stopping.set()
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)

    def __enter__(self) -> FakeHost:
        return self.start()

    def __exit__(self, *exc: object) -> None:
        self.stop()

    def _record(self, kind: str, value: Any) -> None:
        with self._lock:
            if kind == "events":
                self.events.append(value)
            else:
                self.restarts += 1

    @property
    def client_count(self) -> int:
        with self._lock:
            return len(self._clients)

    def push(self, *messages: dict[str, Any]) -> None:
        """Send messages to every connected page, in order."""
        with self._lock:
            for client in self._clients:
                for message in messages:
                    client.put(message)

    def drop_clients(self) -> None:
        """Close every open SSE stream (the page should notice and reconnect)."""
        with self._lock:
            for client in self._clients:
                client.put(_CLOSE)
