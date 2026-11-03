"""Every Python example in the student docs must run in the playground."""

from __future__ import annotations

import contextlib
import re
from pathlib import Path
from typing import Any

import core
import pytest
from core import _runtime

DOCS = Path(__file__).resolve().parents[3] / "docs"
FENCE = re.compile(r"^```python\n(.*?)^```", re.S | re.M)
PAGES = [
    path for path in sorted(DOCS.rglob("*.md")) if "developer" not in path.relative_to(DOCS).parts
]


class _Done(Exception):
    """Raised by the fake `wait` to leave `while True:` loops."""


def _examples() -> list[tuple[str, str]]:
    found = []
    for path in PAGES:
        text = path.read_text(encoding="utf-8")
        for number, match in enumerate(FENCE.finditer(text), start=1):
            found.append((f"{path.relative_to(DOCS)}#{number}", match.group(1)))
    return found


EXAMPLES = _examples()


def test_the_docs_have_examples() -> None:
    assert len(EXAMPLES) >= 20


@pytest.mark.parametrize(("where", "source"), EXAMPLES, ids=[where for where, _ in EXAMPLES])
def test_example_runs(where: str, source: str) -> None:
    calls = 0

    def wait(seconds: float = 0) -> None:
        nonlocal calls
        calls += 1
        if calls > 200:
            raise _Done

    namespace: dict[str, Any] = {**core.namespace(), "wait": wait}
    runtime = _runtime.Runtime(lambda message: None)
    runtime.start()
    try:
        with contextlib.suppress(_Done):
            exec(compile(source, where, "exec"), namespace)
    finally:
        runtime.stop()
