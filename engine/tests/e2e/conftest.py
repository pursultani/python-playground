from __future__ import annotations

from collections.abc import Iterator

import pytest
from e2e_helpers import Playground
from playwright.sync_api import Browser


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if "tests/e2e" in item.nodeid.replace("\\", "/"):
            item.add_marker(pytest.mark.e2e)


@pytest.fixture
def pg(chromium: Browser, tmp_path, request) -> Iterator[Playground]:
    playground = Playground(tmp_path, chromium, request.node.name)
    yield playground
    playground.close()
    assert playground.js_errors == [], "JavaScript errors in the page"
    assert playground.console_errors == [], "console errors in the page"
