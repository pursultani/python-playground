"""Python Playground: the pre-loaded API students use to draw and animate."""

from __future__ import annotations

from typing import Any

from .api import canvas, get, on_click, on_key, wait
from .guides import Axis, Grid
from .shapes import Circle, Line, Rectangle, Shape, Text, Triangle

__all__ = [
    "Circle",
    "Rectangle",
    "Triangle",
    "Line",
    "Text",
    "Shape",
    "Grid",
    "Axis",
    "canvas",
    "wait",
    "get",
    "on_click",
    "on_key",
]


def namespace() -> dict[str, Any]:
    """Return `{name: object}` for every public name, to pre-load into a student's script."""
    return {name: globals()[name] for name in __all__}
