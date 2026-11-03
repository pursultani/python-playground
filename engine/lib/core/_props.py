"""Property descriptors and the validators that give students friendly errors."""

from __future__ import annotations

import math
from collections.abc import Callable
from difflib import get_close_matches
from typing import Any

from ._colors import is_color, suggest_color

Validator = Callable[[str, Any], Any]

NOT_READY = "Call super().__init__() before using properties"


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def number(name: str, value: Any) -> Any:
    """Accept an int or float (not a bool, NaN or infinity)."""
    if not _is_number(value):
        raise TypeError(f"{name} must be a number, but got {value!r}")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number, but got {value!r}")
    return value


def positive_number(name: str, value: Any) -> Any:
    """Accept a number greater than 0."""
    number(name, value)
    if value <= 0:
        raise ValueError(f"{name} must be more than 0, but got {value!r}")
    return value


def non_negative_number(name: str, value: Any) -> Any:
    """Accept a number that is 0 or more."""
    number(name, value)
    if value < 0:
        raise ValueError(f"{name} must be 0 or more, but got {value!r}")
    return value


def opacity_value(name: str, value: Any) -> Any:
    """Accept a number from 0 to 1."""
    number(name, value)
    if not 0 <= value <= 1:
        raise ValueError(f"{name} must be between 0 and 1, but got {value!r}")
    return value


def boolean(name: str, value: Any) -> Any:
    """Accept only True or False."""
    if not isinstance(value, bool):
        raise TypeError(f"{name} must be True or False, but got {value!r}")
    return value


def text(name: str, value: Any) -> Any:
    """Accept a string."""
    if not isinstance(value, str):
        raise TypeError(f'{name} must be text (like "hello"), but got {value!r}')
    return value


def optional_text(name: str, value: Any) -> Any:
    """Accept a string or None."""
    if value is not None and not isinstance(value, str):
        raise TypeError(f'{name} must be text (like "hello") or None, but got {value!r}')
    return value


def to_text(name: str, value: Any) -> Any:
    """Accept anything and turn it into a string with `str()`."""
    return value if isinstance(value, str) else str(value)


def colour(name: str, value: Any) -> Any:
    """Accept a CSS colour: a name, `#rgb`/`#rrggbb` code, or `rgb()`/`hsl()` form."""
    expected = f'{name} must be a color name like "red" or a code like "#ff8800"'
    if not isinstance(value, str):
        raise TypeError(f"{expected}, but got {value!r}")
    if not is_color(value):
        hint = suggest_color(value)
        extra = f" Did you mean {hint!r}?" if hint else ""
        raise ValueError(f"{expected}, but got {value!r}.{extra}")
    return value


def choice(*options: str) -> Validator:
    """Build a validator that accepts one of the given strings."""
    listed = ", ".join(repr(option) for option in options)

    def check(name: str, value: Any) -> Any:
        if not isinstance(value, str):
            raise TypeError(f"{name} must be one of {listed}, but got {value!r}")
        if value not in options:
            matches = get_close_matches(value, options, n=1)
            extra = f" Did you mean {matches[0]!r}?" if matches else ""
            raise ValueError(f"{name} must be one of {listed}, but got {value!r}.{extra}")
        return value

    return check


class Prop:
    """A validated property stored on the owning object's `_values` dict."""

    def __init__(self, default: Any, validator: Validator, sync: bool = True) -> None:
        self.default = default
        self.validator = validator
        self.sync = sync
        self.name = ""

    def __set_name__(self, owner: type, name: str) -> None:
        self.name = name

    def __get__(self, obj: Any, owner: type | None = None) -> Any:
        if obj is None:
            return self
        values = obj.__dict__.get("_values")
        if values is None:
            raise RuntimeError(NOT_READY)
        if self.name not in type(obj)._props:
            raise AttributeError(self.name)
        return values[self.name]

    def __set__(self, obj: Any, value: Any) -> None:
        if "_values" not in obj.__dict__:
            raise RuntimeError(NOT_READY)
        obj._change(self.name, self.validator(self.name, value))


def prop(default: Any, validator: Validator, sync: bool = True) -> Any:
    """Declare a property: `radius: float = prop(50, positive_number)`.

    `sync=False` keeps the property out of the messages sent to the browser.
    """
    return Prop(default, validator, sync)
