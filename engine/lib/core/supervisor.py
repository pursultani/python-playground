"""The host process: HTTP/SSE server, file watcher and child-process manager.

See ``docs/developer/specs/protocol.md``. Typical use::

    supervisor = Supervisor("main.py", port=8765, open_browser=True)
    supervisor.start()
    ...
    supervisor.stop()
"""

from __future__ import annotations

import contextlib
import json
import os
import queue
import select
import signal
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast
from urllib.parse import unquote, urlsplit

from core import _protocol as proto
from core._errors import describe_error

PACKAGE_DIR = Path(__file__).resolve().parent
LIB_DIR = PACKAGE_DIR.parent
STATIC_DIR = PACKAGE_DIR / "static"

KEEPALIVE_SECONDS = 15.0
KILL_GRACE_SECONDS = 1.0
MAX_BODY_BYTES = 64 * 1024
MAX_CLIENT_BACKLOG = 5000
SSE_RETRY = b"retry: 500\n\n"
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
MAX_DIR_ENTRIES = 200
MAX_WATCHED_DIRS = 50
MAX_WATCHED_FILES = 500
SKIPPED_DIRS = {"venv", "env", "node_modules", "site-packages", "__pycache__"}
HARMLESS_MODULE_NAMES = {"test", "this", "antigravity", "idlelib"}
CHILD_BOOT = (
    "import os,sys;c=os.getcwd();"
    "sys.path[:]=[p for p in sys.path if p and os.path.abspath(p)!=c];"
    "from core.runner import run;run()"
)

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
    ".txt": "text/plain; charset=utf-8",
}


class PortUnavailable(Exception):
    """No port could be bound in the requested range."""

    def __init__(self, first: int, last: int) -> None:
        super().__init__(f"ports {first}-{last} are busy")
        self.first = first
        self.last = last


def default_child_argv(script: str) -> list[str]:
    """The command that runs a script in a child process."""
    return [sys.executable, "-u", "-c", CHILD_BOOT, script]


def _authority(value: str) -> tuple[str, int] | None:
    """Split ``host`` or ``host:port`` (``[::1]:port`` too) into ``(host, port)``.

    A missing port means 80. Anything odd (``@``, slashes, spaces, a bad port) gives ``None``.
    """
    value = value.strip()
    if not value or any(char in value for char in "@/\\?# \t\r\n"):
        return None
    if value.startswith("["):
        host, bracket, rest = value[1:].partition("]")
        if not bracket or (rest and not rest.startswith(":")):
            return None
        port_text = rest[1:]
    else:
        host, colon, port_text = value.rpartition(":")
        if not colon:
            host, port_text = value, ""
    if not host or (port_text and not (port_text.isascii() and port_text.isdigit())):
        return None
    port = int(port_text) if port_text else 80
    return (host.lower(), port) if port <= 65535 else None


def _origin_authority(value: str) -> tuple[str, int] | None:
    try:
        parts = urlsplit(value.strip())
    except ValueError:
        return None
    if parts.scheme != "http" or not parts.netloc:
        return None
    return _authority(parts.netloc)


def _is_local(authority: tuple[str, int] | None, port: int) -> bool:
    return authority is not None and authority[0] in LOCAL_HOSTS and authority[1] == port


def _is_home_or_root(directory: Path) -> bool:
    try:
        real = directory.resolve()
        return real == real.parent or real == Path.home().resolve()
    except (OSError, RuntimeError):
        return False


def _scan_python_files(script_dir: Path, descend: bool = True) -> dict[str, tuple[int, int]]:
    """Map every watched ``*.py`` file to ``(mtime_ns, size)``.

    Watches the script directory and, if ``descend``, one level of sub-directories. Hidden,
    ``__*__``, virtual-environment and ``node_modules`` folders are skipped, and so is any
    sub-directory with more than ``MAX_DIR_ENTRIES`` entries, so the work stays small.
    """
    found: dict[str, tuple[int, int]] = {}
    subdirs: list[str] = []

    def scan(directory: str, top: bool) -> None:
        try:
            with os.scandir(directory) as iterator:
                count = 0
                for entry in iterator:
                    count += 1
                    if not top and count > MAX_DIR_ENTRIES:
                        return
                    if len(found) >= MAX_WATCHED_FILES:
                        return
                    try:
                        if entry.name.endswith(".py"):
                            if entry.is_file():
                                info = entry.stat()
                                found[entry.path] = (info.st_mtime_ns, info.st_size)
                        elif (
                            top
                            and descend
                            and len(subdirs) < MAX_WATCHED_DIRS
                            and not entry.name.startswith((".", "__"))
                            and entry.name not in SKIPPED_DIRS
                            and entry.is_dir()
                        ):
                            subdirs.append(entry.path)
                    except OSError:
                        continue
        except OSError:
            return

    scan(str(script_dir), True)
    for path in subdirs:
        scan(path, False)
    return found


def shadowing_warnings(script_dir: Path, script_name: str) -> list[str]:
    """Plain-English warnings for ``*.py`` files named like a module that comes with Python."""
    try:
        names = sorted(entry.name for entry in os.scandir(script_dir) if entry.name.endswith(".py"))
    except OSError:
        return []
    stdlib: frozenset[str] = getattr(sys, "stdlib_module_names", frozenset())
    warnings: list[str] = []
    for name in names:
        stem = name[:-3]
        suggestion = f"my_{stem}.py"
        if stem == "core":
            warnings.append(
                f"{name} has the same name as the Python Playground engine, so a file that says "
                f"import core would not get this one. Rename it, for example {suggestion}."
            )
        elif stem in stdlib and stem not in HARMLESS_MODULE_NAMES and not stem.startswith("__"):
            if name == script_name:
                warnings.append(
                    f"{name} has the same name as a Python module that comes with Python. "
                    f"It still runs, but import {stem} gives you Python's own {stem}, not this "
                    f"file. Rename it, for example {suggestion}."
                )
            else:
                warnings.append(
                    f"{name} has the same name as a Python module that comes with Python, so "
                    f"Python's own {stem} can't be used. Rename it, for example {suggestion}."
                )
    return warnings


class _Client:
    """One connected browser: a queue of already-encoded SSE blocks."""

    def __init__(self) -> None:
        self.queue: queue.Queue[bytes | None] = queue.Queue(maxsize=MAX_CLIENT_BACKLOG)
        self.closed = False


class _Child:
    """A running child process and the pipes to talk to it."""

    def __init__(self, process: subprocess.Popen[bytes]) -> None:
        self.process = process
        self.ended = False
        assert process.stdin is not None and process.stdout is not None
        self.stdout = process.stdout
        self._stdin = proto.JsonLineWriter(process.stdin)

    def send(self, message: dict[str, Any]) -> None:
        with contextlib.suppress(OSError, ValueError):
            self._stdin.write(message)

    def _stop_tree(self, hard: bool) -> None:
        """Ask (or, if ``hard``, force) the child and everything it started to stop."""
        process = self.process
        if os.name == "nt":
            with contextlib.suppress(OSError):
                process.kill() if hard else process.terminate()
            return
        with contextlib.suppress(OSError):
            os.killpg(process.pid, signal.SIGKILL if hard else signal.SIGTERM)

    def sweep(self) -> None:
        """Kill programs the child started and left running (it leads its own session)."""
        if os.name != "nt":
            self._stop_tree(hard=True)

    def kill(self) -> None:
        process = self.process
        if process.poll() is None:
            self._stop_tree(hard=False)
            try:
                process.wait(timeout=KILL_GRACE_SECONDS)
            except subprocess.TimeoutExpired:
                self._stop_tree(hard=True)
                process.wait()
        self.sweep()
        try:
            if process.stdin is not None:
                process.stdin.close()
        except (OSError, ValueError):
            pass


class Supervisor:
    """Runs a script in a child process and serves the browser page that shows it.

    Args:
        script: The Python file to run.
        port: Port to listen on (127.0.0.1 only). ``0`` picks a free one.
        open_browser: Open the page in the default browser on ``start()``.
        port_tries: How many extra ports to try after ``port`` if it is busy.
        log: Called with each short status line meant for the terminal.
        static_dir: Where the page files live (for tests).
        child_argv: Builds the child command from the script path (for tests).
        poll_interval: Seconds between file-change checks.
        keepalive_interval: Seconds between SSE keep-alive comments.
    """

    def __init__(
        self,
        script: str | os.PathLike[str],
        port: int = 0,
        open_browser: bool = False,
        *,
        port_tries: int = 0,
        log: Callable[[str], None] | None = None,
        static_dir: str | os.PathLike[str] | None = None,
        child_argv: Callable[[str], list[str]] | None = None,
        poll_interval: float = 0.25,
        keepalive_interval: float = KEEPALIVE_SECONDS,
    ) -> None:
        self.script = Path(script).absolute()
        self.script_dir = self.script.parent
        self.requested_port = port
        self.open_browser = open_browser
        self.port_tries = port_tries
        self.static_dir = Path(static_dir) if static_dir is not None else STATIC_DIR
        self.poll_interval = poll_interval
        self.keepalive_interval = keepalive_interval
        self._log = log or (lambda line: None)
        self._child_argv = child_argv or default_child_argv

        self._lock = threading.RLock()
        self._changed = threading.Condition(self._lock)
        self._restart_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._mirror = proto.SceneMirror(self.script.name)
        self._clients: list[_Client] = []
        self._child: _Child | None = None
        self._run = 0
        self._warned: set[str] = set()
        self._watch_subdirs = not _is_home_or_root(self.script_dir)
        self._server: _Server | None = None
        self._threads: list[threading.Thread] = []
        self.port = 0

    @property
    def url(self) -> str:
        """Address of the page."""
        return f"http://127.0.0.1:{self.port}/"

    @property
    def state(self) -> str:
        """Current lifecycle state of the program."""
        with self._lock:
            return self._mirror.state

    @property
    def run(self) -> int:
        """Number of the current run (1 for the first)."""
        with self._lock:
            return self._mirror.run

    @property
    def client_count(self) -> int:
        """How many browsers are connected to ``/events``."""
        with self._lock:
            return len(self._clients)

    def snapshot(self) -> dict[str, Any]:
        """The ``snapshot`` message a newly connected browser would get now."""
        with self._lock:
            return self._mirror.snapshot()

    def wait_for_state(self, state: str, timeout: float = 10.0, run: int | None = None) -> None:
        """Block until the program reaches ``state`` (in run number ``run``, if given).

        Raises:
            TimeoutError: if that does not happen in ``timeout`` seconds.
        """
        with self._changed:
            reached = self._changed.wait_for(
                lambda: self._mirror.state == state and (run is None or self._mirror.run == run),
                timeout,
            )
            if not reached:
                raise TimeoutError(
                    f"waited {timeout}s for state {state!r} (run {run}); "
                    f"now {self._mirror.state!r} in run {self._mirror.run}"
                )

    def start(self) -> None:
        """Bind the port, start serving, watch the files and start the first run.

        Raises:
            PortUnavailable: if no port in the allowed range could be bound.
        """
        self._server = self._bind()
        self.port = self._server.server_address[1]
        server = self._server
        self._spawn_thread(lambda: server.serve_forever(0.05), "http")
        if not server.serving.wait(5):
            raise RuntimeError("the web server did not start")
        self._spawn_thread(self._watch, "watcher")
        self.restart()
        if self.open_browser:
            threading.Thread(target=self._open_browser, daemon=True).start()

    def stop(self) -> None:
        """Stop the program, close every connection and shut the server down. Safe to repeat."""
        with self._lock:
            if self._stop_event.is_set():
                return
            self._stop_event.set()
            child, self._child = self._child, None
            for client in self._clients:
                self._close_client(client)
            self._clients.clear()
            self._changed.notify_all()
        if child is not None:
            child.kill()
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        for thread in self._threads:
            thread.join(timeout=2)

    def restart(self, reason: str | None = None) -> None:
        """Kill the current child (if any) and start a fresh run.

        ``reason`` is shown on the terminal, e.g. ``main.py changed - restarting``.
        """
        with self._restart_lock:
            if self._stop_event.is_set():
                return
            if reason:
                self._log(reason)
            with self._lock:
                old, self._child = self._child, None
            if old is not None:
                old.kill()
            with self._lock:
                self._run += 1
                self._mirror.reset(self._run)
                self._broadcast({"t": proto.RUN, "run": self._run})
                self._broadcast_status()
                self._announce_shadowing()
            try:
                child = self._spawn()
            except OSError as exc:
                self._fail(f"The program could not be started: {exc.strerror or exc}")
                return
            with self._lock:
                if self._stop_event.is_set():
                    child.kill()
                    return
                self._child = child
            self._spawn_thread(lambda: self._read_child(child), "child-reader")

    def _announce_shadowing(self) -> None:
        warnings = shadowing_warnings(self.script_dir, self.script.name)
        for text in warnings:
            message = {"t": proto.PRINT, "text": f"Warning: {text}\n", "stream": "stderr"}
            self._mirror.apply(message)
            self._broadcast(message)
            if text not in self._warned:
                self._log(f"Warning: {text}")
        self._warned = set(warnings)

    def send_event(self, event: dict[str, Any]) -> None:
        """Forward a validated browser event to the child if the program is running."""
        with self._lock:
            child = self._child
            running = self._mirror.state == proto.RUNNING
        if child is not None and running:
            child.send(event)

    def subscribe(self) -> _Client:
        """Register a browser. Its queue starts with the ``snapshot``."""
        client = _Client()
        with self._lock:
            client.queue.put_nowait(proto.sse_event(self._mirror.snapshot()))
            if self._stop_event.is_set():
                self._close_client(client)
            else:
                self._clients.append(client)
        return client

    def unsubscribe(self, client: _Client) -> None:
        """Forget a browser."""
        with self._lock:
            if client in self._clients:
                self._clients.remove(client)

    def wait_until_stopped(self) -> None:
        """Block until ``stop()`` is called. Interruptible with Ctrl+C."""
        while not self._stop_event.wait(0.5):
            pass

    def _bind(self) -> _Server:
        first = self.requested_port
        last = first + self.port_tries if first else first
        for candidate in range(first, last + 1):
            try:
                server = _Server(("127.0.0.1", candidate), _Handler)
            except OSError:
                if not first:
                    raise
                continue
            server.supervisor = self
            return server
        raise PortUnavailable(first, last)

    def _spawn_thread(self, target: Callable[[], None], name: str) -> None:
        thread = threading.Thread(target=target, name=f"playground-{name}", daemon=True)
        self._threads = [t for t in self._threads if t.is_alive()]
        self._threads.append(thread)
        thread.start()

    def _open_browser(self) -> None:
        with contextlib.suppress(Exception):
            webbrowser.open(self.url)

    def _spawn(self) -> _Child:
        env = dict(os.environ)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PYTHONPATH"] = os.pathsep.join(
            [str(LIB_DIR)] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])
        )
        process = subprocess.Popen(
            self._child_argv(str(self.script)),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            cwd=self.script_dir,
            env=env,
            start_new_session=True,
        )
        return _Child(process)

    def _read_child(self, child: _Child) -> None:
        try:
            for message in proto.read_messages(child.stdout):
                self._on_message(child, message)
        finally:
            child.process.wait()
            child.sweep()
            child.stdout.close()
            self._on_exit(child)

    def _on_message(self, child: _Child, message: dict[str, Any]) -> None:
        kind = message.get("t")
        with self._lock:
            if child is not self._child or child.ended:
                return
            if kind == proto.HELLO:
                if self._mirror.state == proto.STARTING:
                    self._set_state(proto.RUNNING)
            elif kind in (proto.FRAME, proto.CANVAS, proto.PRINT):
                self._mirror.apply(message)
                self._broadcast(message)
            elif kind == proto.END:
                child.ended = True
                self._set_state(proto.FINISHED)
                self._log("Program finished")
            elif kind == proto.ERROR:
                child.ended = True
                self._crash(message)

    def _on_exit(self, child: _Child) -> None:
        with self._lock:
            if child is not self._child or child.ended:
                return
            child.ended = True
            self._fail("The program stopped unexpectedly")

    def _fail(self, message: str) -> None:
        self._crash(
            {"t": proto.ERROR, "kind": "Error", "message": message, "frames": [], "context": []}
        )

    def _crash(self, payload: dict[str, Any]) -> None:
        with self._lock:
            self._mirror.apply(payload)
            self._broadcast(payload)
            self._set_state(proto.CRASHED)
            self._log(f"Program stopped by an error: {describe_error(payload)}")

    def _set_state(self, state: str) -> None:
        with self._lock:
            self._mirror.state = state
            self._broadcast_status()
            self._changed.notify_all()

    def _broadcast_status(self) -> None:
        self._broadcast({"t": proto.STATUS, "run": self._mirror.run, "state": self._mirror.state})

    def _broadcast(self, message: dict[str, Any]) -> None:
        data = proto.sse_event(message)
        with self._lock:
            for client in list(self._clients):
                try:
                    client.queue.put_nowait(data)
                except queue.Full:
                    self._close_client(client)
                    self._clients.remove(client)

    @staticmethod
    def _close_client(client: _Client) -> None:
        client.closed = True
        with contextlib.suppress(queue.Full):
            client.queue.put_nowait(None)

    def _watch(self) -> None:
        settle = self.poll_interval / 2
        before = _scan_python_files(self.script_dir, self._watch_subdirs)
        while not self._stop_event.wait(self.poll_interval):
            now = _scan_python_files(self.script_dir, self._watch_subdirs)
            if now == before:
                continue
            while True:
                if self._stop_event.wait(settle):
                    return
                again = _scan_python_files(self.script_dir, self._watch_subdirs)
                if again == now:
                    break
                now = again
            changed = sorted(p for p in now.keys() | before.keys() if now.get(p) != before.get(p))
            before = now
            name = os.path.relpath(changed[0], self.script_dir) if changed else self.script.name
            self.restart(f"{name.replace(os.sep, '/')} changed - restarting")


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 64
    supervisor: Supervisor

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.serving = threading.Event()

    def service_actions(self) -> None:
        self.serving.set()

    def handle_error(self, request: Any, client_address: Any) -> None:
        if isinstance(sys.exc_info()[1], (ConnectionError, TimeoutError)):
            return
        super().handle_error(request, client_address)


def _peer_closed(sock: socket.socket) -> bool:
    try:
        readable, _, _ = select.select([sock], [], [], 0)
        return bool(readable) and sock.recv(1, socket.MSG_PEEK) == b""
    except (OSError, ValueError):
        return True


class _Handler(BaseHTTPRequestHandler):
    timeout = 30

    def log_message(self, format: str, *args: Any) -> None:
        pass

    @property
    def supervisor(self) -> Supervisor:
        return cast(_Server, self.server).supervisor

    def _respond(
        self, status: int, body: bytes = b"", content_type: str = "text/plain; charset=utf-8"
    ) -> None:
        self.send_response(status)
        self.send_header("Cache-Control", "no-store")
        if status != 204:
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            if content_type.startswith("text/html"):
                self.send_header("X-Frame-Options", "DENY")
                self.send_header("Content-Security-Policy", "frame-ancestors 'none'")
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _allowed(self, is_post: bool) -> bool:
        own_port = cast(_Server, self.server).server_address[1]
        host = self.headers.get("Host")
        origin = self.headers.get("Origin") if is_post else None
        ok = True
        if host is not None:
            ok = _is_local(_authority(host), own_port)
        if ok and origin is not None:
            ok = _is_local(_origin_authority(origin), own_port)
        if not ok:
            self._respond(403, b"Forbidden: this page only works on this computer.\n")
        return ok

    def _path(self) -> str:
        return self.path.split("?", 1)[0].split("#", 1)[0]

    def do_GET(self) -> None:
        if not self._allowed(False):
            return
        path = self._path()
        if path in ("/", "/index.html"):
            self._serve_static("index.html")
        elif path.startswith("/static/"):
            self._serve_static(path[len("/static/") :])
        elif path == "/events":
            self._serve_events()
        elif path == "/favicon.ico":
            if not self._serve_static("favicon.ico", quiet=True):
                self._respond(204)
        else:
            self._respond(404, b"Not found\n")

    def do_POST(self) -> None:
        if not self._allowed(True):
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if not 0 <= length <= MAX_BODY_BYTES:
            self._respond(400, b"Bad request\n")
            return
        body = self.rfile.read(length) if length else b""
        path = self._path()
        if path == "/event":
            try:
                event = proto.validate_event(json.loads(body.decode("utf-8")))
            except ValueError:
                event = None
            if event is None:
                self._respond(400, b"That is not a valid event.\n")
                return
            self.supervisor.send_event(event)
            self._respond(204)
        elif path == "/restart":
            self.supervisor.restart("Restarting")
            self._respond(204)
        else:
            self._respond(404, b"Not found\n")

    def _static_file(self, relative: str) -> Path | None:
        relative = unquote(relative)
        if not relative or "\x00" in relative or "\\" in relative:
            return None
        root = self.supervisor.static_dir.resolve()
        candidate = (root / relative).resolve()
        try:
            parts = candidate.relative_to(root).parts
        except ValueError:
            return None
        if any(part.startswith(".") for part in parts) or not candidate.is_file():
            return None
        return candidate

    def _serve_static(self, relative: str, quiet: bool = False) -> bool:
        file = self._static_file(relative)
        if file is None:
            if not quiet:
                self._respond(404, b"Not found\n")
            return False
        try:
            body = file.read_bytes()
        except OSError:
            if not quiet:
                self._respond(404, b"Not found\n")
            return False
        self._respond(200, body, CONTENT_TYPES.get(file.suffix.lower(), "application/octet-stream"))
        return True

    def _serve_events(self) -> None:
        supervisor = self.supervisor
        client = supervisor.subscribe()
        last_write = time.monotonic()
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            self.wfile.write(SSE_RETRY)
            self.wfile.flush()
            while not client.closed:
                try:
                    data = client.queue.get(timeout=0.5)
                except queue.Empty:
                    if _peer_closed(self.connection):
                        return
                    if time.monotonic() - last_write >= supervisor.keepalive_interval:
                        self.wfile.write(b": keep-alive\n\n")
                        last_write = time.monotonic()
                    continue
                if data is None:
                    return
                self.wfile.write(data)
                last_write = time.monotonic()
        except (OSError, ValueError):
            pass
        finally:
            supervisor.unsubscribe(client)
            self.close_connection = True
