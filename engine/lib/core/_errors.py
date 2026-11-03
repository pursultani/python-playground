"""Turn an uncaught exception into the error payload the browser shows.

Only frames from the student's own files are kept. See ``protocol.md`` ("Error payload").
"""

from __future__ import annotations

import os
import sysconfig
import traceback
from typing import Any

TAB_WIDTH = 4
CONTEXT_BEFORE = 2
CONTEXT_AFTER = 1
KEEP_FIRST_FRAMES = 5
KEEP_LAST_FRAMES = 15

_PACKAGE_DIR = os.path.dirname(os.path.realpath(__file__))
_SKIPPED_DIR_NAMES = {"site-packages", "dist-packages", "__pycache__"}


def _library_dirs() -> list[str]:
    paths = sysconfig.get_paths()
    found = [_PACKAGE_DIR]
    for key in ("stdlib", "platstdlib", "purelib", "platlib"):
        value = paths.get(key)
        if value:
            found.append(os.path.realpath(value))
    return found


_LIBRARY_DIRS = _library_dirs()


def _is_inside(path: str, root: str) -> bool:
    try:
        return os.path.commonpath([path, root]) == root
    except ValueError:
        return False


def _user_relpath(filename: str | None, script_dir: str) -> tuple[str, str] | None:
    """Return ``(real path, path relative to script_dir)`` for a student's file, else ``None``."""
    if not filename or filename.startswith("<") or not filename.endswith(".py"):
        return None
    real = os.path.realpath(filename)
    if not _is_inside(real, script_dir):
        return None
    if any(_is_inside(real, root) and not _is_inside(script_dir, root) for root in _LIBRARY_DIRS):
        return None
    relative = os.path.relpath(real, script_dir)
    parts = relative.split(os.sep)
    if any(part in _SKIPPED_DIR_NAMES for part in parts):
        return None
    return real, "/".join(parts)


class _Sources:
    """Reads source files once each, as lists of lines (without newline characters)."""

    def __init__(self) -> None:
        self._cache: dict[str, list[str]] = {}

    def lines(self, path: str) -> list[str]:
        if path not in self._cache:
            try:
                with open(path, encoding="utf-8-sig", errors="replace") as handle:
                    lines = handle.read().split("\n")
            except OSError:
                lines = []
            if lines and lines[-1] == "":
                lines.pop()
            self._cache[path] = lines
        return self._cache[path]

    def line(self, path: str, number: int | None) -> str | None:
        lines = self.lines(path)
        if number is not None and 1 <= number <= len(lines):
            return lines[number - 1]
        return None


def _byte_to_char(line: str, offset: int) -> int:
    """Convert a 0-based UTF-8 byte offset in ``line`` to a 0-based character offset."""
    return len(line.encode("utf-8")[:offset].decode("utf-8", errors="ignore"))


def _expand_tabs(line: str) -> str:
    return line.replace("\t", " " * TAB_WIDTH)


def _shift_for_tabs(line: str, column: int) -> int:
    """Map a 1-based column in ``line`` to the same place after tabs are expanded."""
    return column + line[: column - 1].count("\t") * (TAB_WIDTH - 1)


def _columns(line: str, start: int, end: int | None) -> tuple[int, int]:
    """Turn 0-based ``[start, end)`` character offsets into 1-based, tab-expanded columns."""
    stop = len(line.rstrip())
    if end is None or end <= start:
        end = stop
    if end <= start:
        end = start + 1
    return _shift_for_tabs(line, start + 1), _shift_for_tabs(line, end + 1)


def _frame(
    relative: str,
    function: str,
    line_number: int,
    raw: str | None,
    columns: tuple[int, int] | None,
) -> dict[str, Any]:
    frame: dict[str, Any] = {
        "file": relative,
        "line": line_number,
        "function": function,
        "code": _expand_tabs(raw).strip() if raw is not None else "",
    }
    if columns is not None:
        frame["col"], frame["end_col"] = columns
    return frame


def _summary_frame(summary: Any, relative: str, real: str, sources: _Sources) -> dict[str, Any]:
    number = summary.lineno or 0
    raw = sources.line(real, number)
    if raw is None:
        raw = summary.line or None
    columns = None
    start = getattr(summary, "colno", None)
    if raw is not None and start is not None:
        end = getattr(summary, "end_colno", None)
        if getattr(summary, "end_lineno", number) != number:
            end = None
        begin = _byte_to_char(raw, start)
        finish = _byte_to_char(raw, end) if end is not None else None
        columns = _columns(raw, begin, finish)
    return _frame(relative, summary.name, number, raw, columns)


def _syntax_frame(
    exc: SyntaxError, script_dir: str, sources: _Sources
) -> tuple[str, int, dict[str, Any]] | None:
    found = _user_relpath(exc.filename, script_dir)
    number = exc.lineno
    if found is None or not isinstance(number, int) or number < 1:
        return None
    real, relative = found
    raw = exc.text.rstrip("\r\n") if isinstance(exc.text, str) else None
    if raw is None:
        raw = sources.line(real, number)
    columns = None
    offset = exc.offset
    if raw is not None and isinstance(offset, int) and offset >= 1:
        start = min(offset - 1, len(raw))
        end = getattr(exc, "end_offset", None)
        multiline = getattr(exc, "end_lineno", number) not in (None, number)
        if multiline or not isinstance(end, int) or end <= offset:
            end = None
        else:
            end = min(end - 1, len(raw))
        if end is None and not multiline:
            end = start + 1
        columns = _columns(raw, start, end)
    return real, number, _frame(relative, "<module>", number, raw, columns)


def _message(exc: BaseException) -> str:
    if isinstance(exc, SyntaxError) and exc.msg:
        return str(exc.msg)
    formatted = traceback.TracebackException(
        type(exc), exc, exc.__traceback__, compact=True
    ).format_exception_only()
    text = "".join(formatted).rstrip("\n")
    cls = type(exc)
    for name in (f"{cls.__module__}.{cls.__qualname__}", cls.__qualname__, cls.__name__):
        if text.startswith(name + ": "):
            return text[len(name) + 2 :]
        if text == name:
            return ""
    return text


def _context(path: str, number: int, sources: _Sources) -> list[dict[str, Any]]:
    lines = sources.lines(path)
    first = max(1, number - CONTEXT_BEFORE)
    last = min(len(lines), number + CONTEXT_AFTER)
    return [
        {"line": index, "code": _expand_tabs(lines[index - 1]).rstrip()}
        for index in range(first, last + 1)
    ]


def _fallback(exc: BaseException) -> dict[str, Any]:
    try:
        kind = type(exc).__name__
    except Exception:
        kind = "Error"
    try:
        message = str(exc)
    except Exception:
        message = ""
    return {"t": "error", "kind": kind, "message": message, "frames": [], "context": []}


def _build(exc: BaseException, script_dir: str) -> dict[str, Any]:
    root = os.path.realpath(script_dir)
    sources = _Sources()
    entries: list[tuple[str, int, dict[str, Any]]] = []
    for summary in traceback.extract_tb(exc.__traceback__):
        found = _user_relpath(summary.filename, root)
        if found is not None:
            real, relative = found
            entries.append(
                (real, summary.lineno or 0, _summary_frame(summary, relative, real, sources))
            )
    if isinstance(exc, SyntaxError):
        entry = _syntax_frame(exc, root, sources)
        if entry is not None:
            entries.append(entry)

    context: list[dict[str, Any]] = []
    if entries:
        real, number, _ = entries[-1]
        context = _context(real, number, sources)
    if len(entries) > KEEP_FIRST_FRAMES + KEEP_LAST_FRAMES:
        entries = entries[:KEEP_FIRST_FRAMES] + entries[-KEEP_LAST_FRAMES:]
    return {
        "t": "error",
        "kind": type(exc).__name__,
        "message": _message(exc),
        "frames": [frame for _, _, frame in entries],
        "context": context,
    }


def build_error_payload(exc: BaseException, script_dir: str | os.PathLike[str]) -> dict[str, Any]:
    """Build the ``error`` message for ``exc``. Never raises."""
    try:
        return _build(exc, os.fspath(script_dir))
    except Exception:
        return _fallback(exc)


def describe_error(payload: dict[str, Any]) -> str:
    """One terminal line for an error payload, e.g. ``NameError: ... (main.py, line 3)``."""
    kind, message = payload.get("kind") or "Error", payload.get("message") or ""
    text = f"{kind}: {message}" if message else str(kind)
    frames = payload.get("frames") or []
    if frames:
        last = frames[-1]
        text += f" ({last.get('file')}, line {last.get('line')})"
    return text
