"""Fixtures shared by every browser-driven test (engine/tests/browser and engine/tests/e2e).

There is one Playwright instance and one Chromium per test session: Playwright's sync API
cannot be started twice in the same process.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

try:
    from playwright.sync_api import Browser, Playwright, sync_playwright
except ImportError:  # the e2e dependency group is not installed (make test-min)
    sync_playwright = None


@pytest.fixture(scope="session")
def _playwright() -> Iterator[Playwright]:
    if sync_playwright is None:
        pytest.skip("playwright is not installed (uv sync --group e2e)")
    with sync_playwright() as p:
        yield p


@pytest.fixture(scope="session")
def chromium(_playwright: Playwright) -> Iterator[Browser]:
    try:
        browser = _playwright.chromium.launch()
    except Exception as exc:  # browser binaries missing
        pytest.skip(f"Chromium is not available (make install-browsers): {exc}")
    yield browser
    browser.close()
