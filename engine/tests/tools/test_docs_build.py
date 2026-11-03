"""The documentation site must build with `mkdocs build --strict` and render the API reference."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("mkdocs") is None or importlib.util.find_spec("mkdocstrings") is None,
    reason="mkdocs is not installed (uv sync --group docs)",
)


@pytest.fixture(scope="module")
def site(tmp_path_factory: pytest.TempPathFactory) -> Path:
    target = tmp_path_factory.mktemp("site")
    proc = subprocess.run(
        [sys.executable, "-m", "mkdocs", "build", "--strict", "--site-dir", str(target)],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=300,
        env={**os.environ, "NO_MKDOCS_2_WARNING": "1", "SITE_URL": ""},
    )
    output = proc.stdout + proc.stderr
    assert proc.returncode == 0, output
    assert "WARNING" not in output, output
    return target


def _page(site: Path, name: str) -> str:
    return (site / name / "index.html").read_text(encoding="utf-8")


def test_every_page_is_built(site: Path) -> None:
    assert (site / "index.html").is_file()
    for name in (
        "getting-started",
        "engine",
        "engine/shapes",
        "engine/guides",
        "engine/functions",
        "engine/events",
        "engine/errors",
        "developer/architecture",
        "developer/plan",
        "developer/specs/api",
    ):
        assert (site / name / "index.html").is_file(), name


def test_every_public_name_has_a_reference_entry(site: Path) -> None:
    pages = {
        "engine/shapes": ["Shape", "Circle", "Rectangle", "Triangle", "Line", "Text"],
        "engine/guides": ["Grid", "Axis"],
        "engine/functions": ["canvas", "wait", "get"],
        "engine/events": ["on_click", "on_key"],
    }
    for name, entries in pages.items():
        html = _page(site, name)
        for entry in entries:
            assert f'id="core.{entry}"' in html, f"{entry} missing from {name}"


def test_properties_methods_and_docstring_examples_are_rendered(site: Path) -> None:
    html = _page(site, "engine/shapes")
    for anchor in (
        "core.Circle.radius",
        "core.Rectangle.width",
        "core.Line.x2",
        "core.Text.size",
        "core.Shape.on_click",
        "core.shapes.Object.show",
        "core.shapes.Object.name",
    ):
        assert f'id="{anchor}"' in html, anchor
    assert "Distance from the centre to the edge." in html
    assert "Example" in html
    assert 'id="core.Line.rotation"' not in html
    assert 'id="core.Text.title"' not in html


def test_site_url_is_taken_from_the_environment(tmp_path: Path) -> None:
    target = tmp_path / "site"
    proc = subprocess.run(
        [sys.executable, "-m", "mkdocs", "build", "--site-dir", str(target)],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=300,
        env={**os.environ, "NO_MKDOCS_2_WARNING": "1", "SITE_URL": "https://example.test/pg/"},
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "https://example.test/pg/" in (target / "sitemap.xml").read_text(encoding="utf-8")
