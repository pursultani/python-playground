"""The functions students call: canvas, wait, get, on_click, on_key."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from . import _runtime
from ._props import colour, non_negative_number


def canvas(background: str = "white") -> None:
    """Set the background colour of the canvas. Shapes stay where they are.

    Args:
        background: A colour like `"black"`, `"#0b1026"` or `"rgb(10, 20, 40)"`.

    Example:
        ```python
        canvas(background="midnightblue")
        ```
    """
    colour("background", background)
    _runtime.current().set_background(background)


def wait(seconds: float = 0) -> None:
    """Pause the program, show the changes, and run click and key handlers.

    Handlers only run inside `wait()`, so a program that reacts to events keeps calling it
    in a loop. `wait(0)` shows the changes and handles events without pausing.

    Args:
        seconds: How long to pause. Must be 0 or more.

    Example:
        ```python
        ball = Circle()
        for step in range(100):
            ball.x += 3
            wait(0.02)
        ```
    """
    non_negative_number("seconds", seconds)
    _runtime.current().wait(seconds)


def get(name: str) -> Any:
    """Find the object that was created with this `name`.

    Raises a `LookupError` if no object has that name.

    Args:
        name: The name given with `name="..."`.

    Example:
        ```python
        Circle(name="ball")
        get("ball").color = "red"
        ```
    """
    if not isinstance(name, str):
        raise TypeError(f'get needs a name in quotes, like get("ball"), but got {name!r}')
    return _runtime.current().lookup(name)


def on_click(handler: Callable[..., object] | None) -> None:
    """Call `handler` when the canvas is clicked (and no shape with its own handler is hit).

    The function may take `(x, y)`, just `(x)`, or nothing. Pass `None` to stop. It runs
    inside `wait()`.

    Args:
        handler: The function to call, or `None` to remove the handler.

    Example:
        ```python
        def clicked(x, y):
            Circle(x, y, radius=10)

        on_click(clicked)
        while True:
            wait(0.05)
        ```
    """
    _runtime.current().set_click_handler(_runtime.bind_handler(handler, "on_click", ("x", "y")))


def on_key(handler: Callable[..., object] | None) -> None:
    """Call `handler(key)` when a key is pressed, like `"a"`, `"ArrowLeft"` or `"Space"`.

    The function may take `(key)` or nothing. Pass `None` to stop. It runs inside `wait()`.

    Args:
        handler: The function to call, or `None` to remove the handler.

    Example:
        ```python
        ball = Circle()

        def pressed(key):
            if key == "ArrowRight":
                ball.x += 10

        on_key(pressed)
        while True:
            wait(0.05)
        ```
    """
    _runtime.current().set_key_handler(_runtime.bind_handler(handler, "on_key", ("key",)))
