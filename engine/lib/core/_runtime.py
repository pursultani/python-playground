"""Child-side runtime: pending scene, flusher thread, event queue, wait() and print capture."""

from __future__ import annotations

import contextlib
import inspect
import io
import queue
import threading
import time
from collections.abc import Callable
from difflib import get_close_matches
from typing import Any

from ._scene import Scene

FLUSH_INTERVAL = 1 / 60
# `wait()` flushes at once, but not more often than this, so `while True: wait()` cannot flood
# the browser (the flusher thread sends whatever `wait()` skipped).
MIN_WAIT_FLUSH_INTERVAL = FLUSH_INTERVAL / 2
EVENT_QUEUE_SIZE = 1000
MAX_PRINT_CHARS_PER_FLUSH = 64 * 1024
TOO_MUCH_OUTPUT = (
    "Too much was printed too fast, so some output was skipped. "
    "Try adding wait(0.1) inside your loop.\n"
)


class Handler:
    """An event handler plus how many of the event's values it accepts."""

    __slots__ = ("count", "func")

    def __init__(self, func: Callable[..., Any], count: int | None) -> None:
        self.func = func
        self.count = count

    def call(self, *values: Any) -> None:
        """Call the function with as many of `values` as it accepts."""
        self.func(*(values if self.count is None else values[: self.count]))


def bind_handler(handler: Any, what: str, params: tuple[str, ...]) -> Handler | None:
    """Check a handler given to `on_click`/`on_key` and work out its arity.

    `None` means "remove the handler". Raises a friendly `TypeError` for anything else that
    cannot be called with the event's values.
    """
    if handler is None:
        return None
    given = ", ".join(params)
    if not callable(handler):
        raise TypeError(
            f"{what} needs a function, but got {handler!r}. "
            f"Give the function's name without brackets, like {what}(my_function)."
        )
    try:
        signature = inspect.signature(handler)
    except (TypeError, ValueError):
        return Handler(handler, None)
    positional = 0
    required = 0
    variadic = False
    for param in signature.parameters.values():
        if param.kind in (param.POSITIONAL_ONLY, param.POSITIONAL_OR_KEYWORD):
            positional += 1
            if param.default is param.empty:
                required += 1
        elif param.kind is param.VAR_POSITIONAL:
            variadic = True
        elif param.kind is param.KEYWORD_ONLY and param.default is param.empty:
            required = len(params) + 1
    if required > len(params):
        label = getattr(handler, "__name__", "the function")
        plural = "value" if len(params) == 1 else "values"
        raise TypeError(
            f"{what} can only give its function {len(params)} {plural} ({given}), "
            f"but {label} needs more. Remove the extra parameters."
        )
    return Handler(handler, None if variadic else min(positional, len(params)))


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        return round(value)
    except (OverflowError, ValueError):
        return None


class _PrintStream(io.TextIOBase):
    """File-like object that sends everything written to it to the browser console."""

    def __init__(self, runtime: Runtime, name: str) -> None:
        super().__init__()
        self._runtime = runtime
        self._name = name

    def write(self, text: str) -> int:
        if not isinstance(text, str):
            raise TypeError(f"write() argument must be str, not {type(text).__name__}")
        if text:
            self._runtime._add_print(self._name, text)
        return len(text)

    def writable(self) -> bool:
        return True

    def isatty(self) -> bool:
        return False

    def flush(self) -> None:
        pass


class Runtime:
    """Collects scene changes and console output, sends them on a timer, runs event handlers.

    `send(message)` writes one protocol message. With `send=None` the runtime only records
    things in memory (this is the "null runtime" used when no program is running).
    """

    def __init__(self, send: Callable[[dict[str, Any]], None] | None = None) -> None:
        self._send = send
        self._lock = threading.Lock()
        self._flush_lock = threading.Lock()
        self._last_flush = 0.0
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._events: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=EVENT_QUEUE_SIZE)
        self._prints: list[tuple[str, list[str]]] = []
        self._print_chars = 0
        self._print_skipped = False
        self.scene = Scene()
        self._background: str | None = None
        self._objects: dict[int, Any] = {}
        self._names: dict[str, Any] = {}
        self._click: Handler | None = None
        self._key: Handler | None = None

    def reset(self) -> None:
        """Forget the scene, ids, names, handlers and queued events (a new run begins)."""
        with self._lock:
            self.scene = Scene()
            self._background = None
        self._objects = {}
        self._names = {}
        self._click = None
        self._key = None
        self._drain_events()

    def start(self) -> None:
        """Become the active runtime for a fresh run and start the flusher thread."""
        global _active
        self.reset()
        _active = self
        if self._thread is None or not self._thread.is_alive():
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._flush_forever, name="core-flusher", daemon=True
            )
            self._thread.start()

    def stop(self) -> None:
        """Stop the flusher thread, send everything still pending, and deactivate."""
        global _active
        self._stop_event.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2)
        self._thread = None
        try:
            self.flush()
        finally:
            if _active is self:
                _active = None

    def flush(self) -> None:
        """Send pending canvas, frame and print messages now. Safe from any thread."""
        if self._send is None:
            return
        with self._flush_lock:
            self._last_flush = time.monotonic()
            with self._lock:
                background, self._background = self._background, None
                ops = self.scene.drain()
                prints, self._prints = self._prints, []
                if self._print_skipped:
                    prints.append(("stderr", [self._skipped_notice(prints)]))
                self._print_chars = 0
                self._print_skipped = False
            if background is not None:
                self._send({"t": "canvas", "background": background})
            if ops:
                self._send({"t": "frame", "ops": ops})
            for stream, parts in prints:
                self._send({"t": "print", "text": "".join(parts), "stream": stream})

    def feed_event(self, event: dict[str, Any]) -> None:
        """Queue an event from the browser. Never blocks; drops the event if the queue is full."""
        if not isinstance(event, dict):
            return
        with contextlib.suppress(queue.Full):
            self._events.put_nowait(event)

    def print_stream(self, name: str) -> io.TextIOBase:
        """Return a file-like object for `"stdout"` or `"stderr"` that feeds the console."""
        if name not in ("stdout", "stderr"):
            raise ValueError(f"stream must be 'stdout' or 'stderr', not {name!r}")
        return _PrintStream(self, name)

    def wait(self, seconds: float = 0) -> None:
        """Flush, run queued event handlers, and pause until `seconds` have passed in total."""
        deadline = time.monotonic() + seconds
        self._flush_unless_just_flushed()
        while True:
            self._dispatch_queued()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                event = self._events.get(timeout=min(remaining, 1.0))
            except queue.Empty:
                continue
            self._dispatch(event)
            self._flush_unless_just_flushed()
        self._flush_unless_just_flushed()

    def _flush_unless_just_flushed(self) -> None:
        if time.monotonic() - self._last_flush >= MIN_WAIT_FLUSH_INTERVAL:
            self.flush()

    def register(self, obj: Any, type_: str, props: dict[str, Any]) -> int:
        """Give a new object the next id and queue its `create` op."""
        with self._lock:
            id_ = self.scene.create(type_, props)
        self._objects[id_] = obj
        return id_

    def update(self, id_: int, props: dict[str, Any]) -> None:
        """Queue changed properties for an object."""
        with self._lock:
            self.scene.update(id_, props)

    def unregister(self, id_: int) -> None:
        """Queue the removal of an object."""
        self._objects.pop(id_, None)
        with self._lock:
            self.scene.remove(id_)

    def claim_name(self, name: str, obj: Any) -> None:
        """Reserve `name` for `obj`, or raise `ValueError` if another object has it."""
        owner = self._names.get(name)
        if owner is not None and owner is not obj:
            raise ValueError(f"There is already an object named {name!r}. Names must be different.")
        self._names[name] = obj

    def release_name(self, name: str | None, obj: Any) -> None:
        """Free `name` if `obj` holds it."""
        if name is not None and self._names.get(name) is obj:
            del self._names[name]

    def lookup(self, name: str) -> Any:
        """Return the live object called `name`, or raise `LookupError`."""
        obj = self._names.get(name)
        if obj is None:
            matches = get_close_matches(name, list(self._names), n=1)
            hint = f" Did you mean {matches[0]!r}?" if matches else ""
            raise LookupError(f"No object is named {name!r}.{hint}")
        return obj

    def set_background(self, color: str) -> None:
        """Queue a new canvas background colour."""
        with self._lock:
            self._background = color

    def set_click_handler(self, handler: Handler | None) -> None:
        """Set (or clear) the handler for clicks that are not on a shape with its own handler."""
        self._click = handler

    def set_key_handler(self, handler: Handler | None) -> None:
        """Set (or clear) the key press handler."""
        self._key = handler

    @staticmethod
    def _skipped_notice(prints: list[tuple[str, list[str]]]) -> str:
        last = prints[-1] if prints else None
        if last is not None and not last[1][-1].endswith("\n"):
            return "\n" + TOO_MUCH_OUTPUT
        return TOO_MUCH_OUTPUT

    def _add_print(self, stream: str, text: str) -> None:
        with self._lock:
            room = MAX_PRINT_CHARS_PER_FLUSH - self._print_chars
            if len(text) > room:
                self._print_skipped = True
                text = text[: max(room, 0)]
                if not text:
                    return
            self._print_chars += len(text)
            if self._prints and self._prints[-1][0] == stream:
                self._prints[-1][1].append(text)
            else:
                self._prints.append((stream, [text]))

    def _drain_events(self) -> None:
        while True:
            try:
                self._events.get_nowait()
            except queue.Empty:
                return

    def _dispatch_queued(self) -> None:
        dispatched = False
        for _ in range(self._events.qsize()):
            try:
                event = self._events.get_nowait()
            except queue.Empty:
                break
            self._dispatch(event)
            dispatched = True
        if dispatched:
            self._flush_unless_just_flushed()

    def _dispatch(self, event: dict[str, Any]) -> None:
        kind = event.get("t")
        if kind == "click":
            x, y = _as_int(event.get("x")), _as_int(event.get("y"))
            if x is None or y is None:
                return
            target = event.get("target")
            shape = self._objects.get(target) if isinstance(target, int) else None
            handler = getattr(shape, "_click", None) or self._click
            if handler is not None:
                handler.call(x, y)
        elif kind == "key":
            key = event.get("key")
            if isinstance(key, str) and self._key is not None:
                self._key.call(key)

    def _flush_forever(self) -> None:
        while not self._stop_event.wait(FLUSH_INTERVAL):
            try:
                self.flush()
            except Exception:
                return


_active: Runtime | None = None
_null = Runtime(None)


def current() -> Runtime:
    """Return the active runtime, or a null runtime that only records things in memory."""
    return _active or _null
