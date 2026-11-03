from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fake_host import FakeHost
from page_driver import App
from playwright.sync_api import Browser


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if "tests/browser" in item.nodeid.replace("\\", "/"):
            item.add_marker(pytest.mark.e2e)


@pytest.fixture
def host() -> Iterator[FakeHost]:
    with FakeHost() as h:
        yield h


@pytest.fixture
def open_app(chromium: Browser, host: FakeHost) -> Iterator[Callable[..., App]]:
    """Return ``open_app(**context_options)``: a page loaded and connected to the fake host."""
    contexts = []
    apps: list[App] = []

    def factory(snapshot: dict[str, Any] | None = None, **options: Any) -> App:
        if snapshot is not None:
            host.snapshot.update(snapshot)
        options.setdefault("viewport", {"width": 1100, "height": 800})
        context = chromium.new_context(**options)
        contexts.append(context)
        page = context.new_page()
        page.set_default_timeout(5000)
        app = App(host, page)
        apps.append(app)
        return app.open()

    yield factory
    for context in contexts:
        context.close()
    for app in apps:
        assert app.js_errors == []


@pytest.fixture
def app(open_app: Callable[..., App]) -> App:
    return open_app()
