from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from core import _runtime


class Recorder:
    """A fake `send` that remembers every message."""

    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    def __call__(self, message: dict[str, Any]) -> None:
        self.messages.append(message)

    def of(self, kind: str) -> list[dict[str, Any]]:
        return [m for m in self.messages if m["t"] == kind]

    def ops(self) -> list[dict[str, Any]]:
        return [op for m in self.of("frame") for op in m["ops"]]


@pytest.fixture(autouse=True)
def _clean_null_runtime() -> Iterator[None]:
    _runtime._null.reset()
    yield
    _runtime._null.reset()


@pytest.fixture
def sent() -> Recorder:
    return Recorder()


@pytest.fixture
def rt(sent: Recorder, monkeypatch: pytest.MonkeyPatch) -> _runtime.Runtime:
    """An active runtime without a flusher thread, so tests control when messages go out."""
    runtime = _runtime.Runtime(sent)
    monkeypatch.setattr(_runtime, "_active", runtime)
    return runtime
