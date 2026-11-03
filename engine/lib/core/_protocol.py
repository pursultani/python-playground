"""Wire-protocol helpers shared by the supervisor (host) and the runner (child).

Messages are JSON objects with a ``"t"`` type, sent one per line. See
``docs/developer/specs/protocol.md`` for the full description.
"""

from __future__ import annotations

import io
import json
import math
import threading
from collections.abc import Iterator
from typing import IO, Any

# Child -> supervisor, and supervisor -> browser.
HELLO = "hello"
FRAME = "frame"
CANVAS = "canvas"
PRINT = "print"
END = "end"
ERROR = "error"

# Supervisor -> browser only.
SNAPSHOT = "snapshot"
RUN = "run"
STATUS = "status"

# Browser -> supervisor -> child.
CLICK = "click"
KEY = "key"

STARTING = "starting"
RUNNING = "running"
FINISHED = "finished"
CRASHED = "crashed"

DEFAULT_BACKGROUND = "white"
MAX_CONSOLE_CHUNKS = 2000
# Adjacent chunks are merged, but a chunk never grows past this, so an endless `print` loop
# cannot make the mirror grow without bound (2000 chunks x 8 KiB at most).
MAX_CHUNK_CHARS = 8192
MAX_KEY_LENGTH = 64


def dumps(message: dict[str, Any]) -> str:
    """Encode one message as compact JSON (no newlines inside)."""
    return json.dumps(message, ensure_ascii=False, separators=(",", ":"))


def sse_event(message: dict[str, Any]) -> bytes:
    """Encode one message as a Server-Sent Events ``data:`` block."""
    return f"data: {dumps(message)}\n\n".encode()


class JsonLineWriter:
    """Writes one JSON object per line to a text or binary stream (thread-safe, flushes)."""

    def __init__(self, stream: IO[Any]) -> None:
        self._stream = stream
        self._binary = not isinstance(stream, io.TextIOBase)
        self._lock = threading.Lock()

    def write(self, message: dict[str, Any]) -> None:
        line = dumps(message) + "\n"
        data = line.encode("utf-8") if self._binary else line
        with self._lock:
            self._stream.write(data)  # type: ignore[arg-type]
            self._stream.flush()


def read_messages(stream: IO[Any]) -> Iterator[dict[str, Any]]:
    """Yield the JSON objects found on each line of ``stream`` until it ends.

    Lines that are blank, not JSON, or not a JSON object are skipped.
    """
    while True:
        raw = stream.readline()
        if not raw:
            return
        line = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except ValueError:
            continue
        if isinstance(message, dict):
            yield message


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def validate_event(raw: Any) -> dict[str, Any] | None:
    """Check a browser event and return it in canonical form, or ``None`` if it is invalid."""
    if not isinstance(raw, dict):
        return None
    kind = raw.get("t")
    if kind == CLICK:
        x: Any = raw.get("x")
        y: Any = raw.get("y")
        target: Any = raw.get("target")
        if not (_is_number(x) and _is_number(y)):
            return None
        if target is not None and (not isinstance(target, int) or isinstance(target, bool)):
            return None
        return {"t": CLICK, "x": round(x), "y": round(y), "target": target}
    if kind == KEY:
        key = raw.get("key")
        if isinstance(key, str) and 0 < len(key) <= MAX_KEY_LENGTH:
            return {"t": KEY, "key": key}
    return None


class SceneMirror:
    """The supervisor's copy of what the browser shows, used to build ``snapshot`` messages.

    Not thread-safe: the owner serialises access.
    """

    def __init__(self, script: str = "") -> None:
        self.script = script
        self.run = 0
        self.state = STARTING
        self.background = DEFAULT_BACKGROUND
        self.objects: dict[int, dict[str, Any]] = {}
        self.console: list[dict[str, str]] = []
        self.error: dict[str, Any] | None = None

    def reset(self, run: int) -> None:
        """Start a new run: blank canvas, empty console, no error, state ``starting``."""
        self.run = run
        self.state = STARTING
        self.background = DEFAULT_BACKGROUND
        self.objects = {}
        self.console = []
        self.error = None

    def apply(self, message: dict[str, Any]) -> None:
        """Fold a ``frame``, ``canvas``, ``print`` or ``error`` message into the mirror."""
        kind = message.get("t")
        if kind == FRAME:
            ops = message.get("ops")
            if isinstance(ops, list):
                for op in ops:
                    self._apply_op(op)
        elif kind == CANVAS:
            background = message.get("background")
            if isinstance(background, str):
                self.background = background
        elif kind == PRINT:
            text = message.get("text")
            if isinstance(text, str):
                self._append_console(text, message.get("stream") == "stderr")
        elif kind == ERROR:
            self.error = message

    def _apply_op(self, op: Any) -> None:
        if not isinstance(op, dict):
            return
        kind = op.get("op")
        object_id: Any = op.get("id")
        props = op.get("props")
        if kind == "create":
            if isinstance(props, dict):
                self.objects[object_id] = {
                    "id": object_id,
                    "type": op.get("type"),
                    "props": dict(props),
                }
        elif kind == "update":
            current = self.objects.get(object_id)
            if current is not None and isinstance(props, dict):
                current["props"].update(props)
        elif kind == "remove":
            self.objects.pop(object_id, None)

    def _append_console(self, text: str, is_stderr: bool) -> None:
        if not text:
            return
        stream = "stderr" if is_stderr else "stdout"
        last = self.console[-1] if self.console else None
        if last is not None and last["stream"] == stream and len(last["text"]) < MAX_CHUNK_CHARS:
            last["text"] += text
            return
        self.console.append({"text": text, "stream": stream})
        if len(self.console) > MAX_CONSOLE_CHUNKS:
            del self.console[: len(self.console) - MAX_CONSOLE_CHUNKS]

    def snapshot(self) -> dict[str, Any]:
        """Build the ``snapshot`` message describing the current state."""
        return {
            "t": SNAPSHOT,
            "run": self.run,
            "state": self.state,
            "script": self.script,
            "background": self.background,
            "objects": [
                {"id": obj["id"], "type": obj["type"], "props": dict(obj["props"])}
                for obj in self.objects.values()
            ],
            "console": [dict(chunk) for chunk in self.console],
            "error": self.error,
        }
