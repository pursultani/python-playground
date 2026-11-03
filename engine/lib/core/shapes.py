"""The base object and the shapes students draw: Circle, Rectangle, Triangle, Line, Text."""

from __future__ import annotations

import functools
import inspect
from collections.abc import Callable
from difflib import get_close_matches
from typing import Any, ClassVar

from . import _runtime
from ._props import (
    NOT_READY,
    Prop,
    boolean,
    colour,
    number,
    opacity_value,
    optional_text,
    positive_number,
    prop,
    text,
    to_text,
)

_MISSING = object()


def _suggest(word: str, candidates: Any, cutoff: float) -> str | None:
    matches = get_close_matches(word, list(candidates), n=1, cutoff=cutoff)
    return matches[0] if matches else None


def _is_plural_of_property(key: str, cls: type) -> bool:
    return any(key in (f"{name}s", f"{name}es") for name in cls._props)  # type: ignore[attr-defined]


def _no_property(cls: type, key: str, hint: str | None) -> AttributeError:
    extra = f" Did you mean {hint!r}?" if hint else ""
    return AttributeError(f"{cls.__name__} has no property {key!r}.{extra}")


def _friendly_init(init: Callable[..., None]) -> Callable[..., None]:
    """Wrap a built-in constructor so mistakes in its arguments read well."""
    params = list(inspect.signature(init).parameters.values())[1:]
    positional = [p.name for p in params if p.kind is p.POSITIONAL_OR_KEYWORD]
    keywords = [p.name for p in params if p.kind is p.KEYWORD_ONLY]

    @functools.wraps(init)
    def wrapper(self: Object, *args: Any, **kwargs: Any) -> None:
        cls = type(self)
        if len(args) > len(positional):
            if not positional:
                first = "size" if "size" in keywords else keywords[0]
                raise TypeError(
                    f"{cls.__name__}() needs names for its values, like {cls.__name__}({first}=50)."
                )
            example = f", like {keywords[0]}=..." if keywords else ""
            raise TypeError(
                f"{cls.__name__}() takes at most {len(positional)} values without a name "
                f"({', '.join(positional)}). Give the others by name{example}"
            )
        for key in positional[: len(args)]:
            if key in kwargs:
                raise TypeError(f"{key} was given twice: once by position and once by name.")
        for key in kwargs:
            if key not in positional and key not in keywords:
                hint = _suggest(key, cls._props, 0.6)
                extra = f" Did you mean {hint!r}?" if hint else ""
                raise TypeError(f"{cls.__name__}() got an unknown property {key!r}.{extra}")
        init(self, *args, **kwargs)

    return wrapper


class Object:
    """Everything that can appear on the canvas: shapes and guides share these members.

    You never create an `Object` yourself. Use `Circle`, `Grid` and friends.
    """

    _type: ClassVar[str] = ""
    _props: ClassVar[dict[str, Prop]] = {}
    _excluded: ClassVar[tuple[str, ...]] = ()
    _builtin: ClassVar[bool] = False
    _values: dict[str, Any]
    _id: int
    _removed: bool

    name: str | None = prop(None, optional_text, sync=False)
    """A secret label for this object, or `None`. Find the object later with `get(name)`.

    Names must be different from each other. Removing the object frees its name.

    Example:
        ```python
        Circle(name="ball")
        get("ball").color = "red"
        ```
    """

    visible: bool = prop(True, boolean)
    """`True` if the object is drawn, `False` if it is hidden.

    Example:
        ```python
        ball = Circle()
        ball.visible = False
        ```
    """

    opacity: float = prop(1, opacity_value)
    """How solid the object is, from 0 (invisible) to 1 (fully solid).

    Example:
        ```python
        ghost = Circle(opacity=0.3)
        ghost.opacity = 0.8
        ```
    """

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        cls._builtin = cls.__module__.startswith("core.")
        props: dict[str, Prop] = {}
        for base in reversed(cls.__mro__):
            own = vars(base)
            props.update({key: value for key, value in own.items() if isinstance(value, Prop)})
            for key in own.get("_excluded", ()):
                props.pop(key, None)
        last = [key for key, value in vars(Object).items() if isinstance(value, Prop)]
        cls._props = {k: v for k, v in props.items() if k not in last}
        cls._props.update({key: props[key] for key in last if key in props})
        if cls._builtin and "__init__" in vars(cls):
            cls.__init__ = _friendly_init(vars(cls)["__init__"])  # type: ignore[method-assign]

    def _setup(self, props: dict[str, Any]) -> None:
        """Validate every property in `props` (a constructor's `locals()`), then queue `create`."""
        cls = type(self)
        if not cls._type:
            if cls is Shape:
                raise TypeError(
                    "Shape can't be used directly. "
                    "Use Circle, Rectangle, Triangle, Line or Text instead."
                )
            raise TypeError(
                f"{cls.__name__} has no shape of its own. "
                "Make it a subclass of Circle, Rectangle, Triangle, Line or Text."
            )
        if "_values" in self.__dict__:
            raise RuntimeError(
                "super().__init__() was called twice. Call it only once, at the start of __init__."
            )
        values: dict[str, Any] = {}
        for key, prop_ in cls._props.items():
            values[key] = prop_.validator(key, props[key]) if key in props else prop_.default
        runtime = _runtime.current()
        runtime.ensure_room()
        if values.get("name") is not None:
            runtime.claim_name(values["name"], self)
        synced = {key: value for key, value in values.items() if cls._props[key].sync}
        self._values = values
        self._removed = False
        self._id = runtime.register(self, cls._type, synced)

    def _change(self, key: str, value: Any) -> None:
        if self._removed:
            return
        runtime = _runtime.current()
        if key == "name":
            old = self._values["name"]
            if value != old:
                if value is not None:
                    runtime.claim_name(value, self)
                runtime.release_name(old, self)
        self._values[key] = value
        if type(self)._props[key].sync:
            runtime.update(self._id, {key: value})

    def __setattr__(self, key: str, value: Any) -> None:
        cls = type(self)
        if key in cls._props or key.startswith("_") or key in self.__dict__:
            object.__setattr__(self, key, value)
            return
        existing = getattr(cls, key, _MISSING)
        if cls._builtin or isinstance(existing, Prop):
            raise _no_property(cls, key, _suggest(key, cls._props, 0.6))
        hint = None
        if existing is _MISSING and not _is_plural_of_property(key, cls):
            hint = _suggest(key, cls._props, 0.85)
        if hint:
            raise _no_property(cls, key, hint)
        object.__setattr__(self, key, value)

    def __getattr__(self, key: str) -> Any:
        cls = type(self)
        if not key.startswith("_"):
            methods = [n for n in dir(cls) if not n.startswith("_") and callable(getattr(cls, n))]
            if cls._builtin:
                raise _no_property(cls, key, _suggest(key, [*cls._props, *methods], 0.6))
            hint = None if _is_plural_of_property(key, cls) else _suggest(key, cls._props, 0.85)
            if hint:
                raise _no_property(cls, key, hint)
        raise AttributeError(f"{cls.__name__!r} object has no attribute {key!r}")

    def show(self) -> None:
        """Make the object visible. Same as `visible = True`.

        Example:
            ```python
            ball = Circle()
            ball.hide()
            ball.show()
            ```
        """
        self.visible = True

    def hide(self) -> None:
        """Hide the object. Same as `visible = False`.

        Example:
            ```python
            ball = Circle()
            ball.hide()
            ```
        """
        self.visible = False

    def remove(self) -> None:
        """Delete the object from the canvas for good and free its `name`.

        Changing a removed object later does nothing.

        Example:
            ```python
            ball = Circle(name="ball")
            ball.remove()
            Circle(name="ball")  # the name can be used again
            ```
        """
        if "_values" not in self.__dict__:
            raise RuntimeError(NOT_READY)
        if self._removed:
            return
        self._removed = True
        runtime = _runtime.current()
        runtime.release_name(self._values["name"], self)
        runtime.unregister(self._id)

    def __repr__(self) -> str:
        """Show the class name and the properties that are not at their default."""
        cls = type(self)
        values = self.__dict__.get("_values")
        if values is None:
            return f"{cls.__name__}()"
        shown = [
            f"{key}={values[key]!r}"
            for key, prop_ in cls._props.items()
            if key in ("x", "y") or values[key] != prop_.default
        ]
        return f"{cls.__name__}({', '.join(shown)})"


class Shape(Object):
    """Base class of every shape. Make a `Circle`, `Rectangle`, `Triangle`, `Line` or `Text`.

    Subclass a concrete shape to give it your own attributes and methods.

    Example:
        ```python
        class Player(Circle):
            def __init__(self):
                super().__init__(x=0, y=-200, color="orange", name="player")
                self.speed = 10
        ```
    """

    _click: _runtime.Handler | None = None

    x: float = prop(0, number)
    """Horizontal position of the shape's centre. 0 is the middle, positive is right.

    Example:
        ```python
        ball = Circle()
        ball.x = 100
        ```
    """

    y: float = prop(0, number)
    """Vertical position of the shape's centre. 0 is the middle, positive is up.

    Example:
        ```python
        ball = Circle()
        ball.y = -80
        ```
    """

    color: str = prop("steelblue", colour)
    """The colour, like `"red"`, `"#ff8800"` or `"rgb(255, 136, 0)"`.

    Example:
        ```python
        ball = Circle()
        ball.color = "tomato"
        ```
    """

    rotation: float = prop(0, number)
    """Turn the shape about its centre, in degrees, counter-clockwise.

    Example:
        ```python
        box = Rectangle()
        box.rotation = 45
        ```
    """

    title: str = prop("", text)
    """A label drawn at the centre of the shape. Empty means no label.

    Example:
        ```python
        sun = Circle(radius=80, color="gold")
        sun.title = "Sun"
        ```
    """

    def __init__(
        self,
        x: float = 0,
        y: float = 0,
        *,
        color: str = "steelblue",
        rotation: float = 0,
        title: str = "",
        name: str | None = None,
        visible: bool = True,
        opacity: float = 1,
    ) -> None:
        """You can't make a plain `Shape`. Use `Circle`, `Rectangle`, `Triangle`, `Line` or `Text`.

        Args:
            x: Horizontal position of the centre.
            y: Vertical position of the centre.
            color: The colour.
            rotation: Turn in degrees, counter-clockwise.
            title: A label drawn on the shape.
            name: A secret label for `get(name)`.
            visible: `False` to start hidden.
            opacity: 0 (invisible) to 1 (solid).
        """
        self._setup(locals())

    def on_click(self, handler: Callable[..., object] | None) -> None:
        """Call `handler` when this shape is clicked. Pass `None` to stop.

        The function may take `(x, y)`, just `(x)`, or nothing at all. It runs inside `wait()`.

        Args:
            handler: The function to call, or `None` to remove the handler.

        Example:
            ```python
            ball = Circle()

            def pop():
                ball.color = "red"

            ball.on_click(pop)
            while True:
                wait(0.05)
            ```
        """
        self._click = _runtime.bind_handler(handler, "on_click", ("x", "y"))


class Circle(Shape):
    """A circle. `Circle(100, 50)` puts it at x=100, y=50.

    Example:
        ```python
        ball = Circle(100, 50, radius=40, color="orange")
        ```
    """

    _type = "circle"

    radius: float = prop(50, positive_number)
    """Distance from the centre to the edge. Must be more than 0.

    Example:
        ```python
        ball = Circle()
        ball.radius = 80
        ```
    """

    def __init__(
        self,
        x: float = 0,
        y: float = 0,
        *,
        radius: float = 50,
        color: str = "steelblue",
        rotation: float = 0,
        title: str = "",
        name: str | None = None,
        visible: bool = True,
        opacity: float = 1,
    ) -> None:
        """Draw a circle.

        Args:
            x: Horizontal position of the centre.
            y: Vertical position of the centre.
            radius: Distance from the centre to the edge.
            color: The colour.
            rotation: Turn in degrees, counter-clockwise.
            title: A label drawn on the circle.
            name: A secret label for `get(name)`.
            visible: `False` to start hidden.
            opacity: 0 (invisible) to 1 (solid).

        Example:
            ```python
            Circle(0, 0, radius=60, color="gold", title="Sun")
            ```
        """
        self._setup(locals())


class Rectangle(Shape):
    """A rectangle centred on `x, y`.

    Example:
        ```python
        box = Rectangle(-100, 0, width=80, height=50, color="seagreen")
        ```
    """

    _type = "rectangle"

    width: float = prop(100, positive_number)
    """How wide the rectangle is. Must be more than 0.

    Example:
        ```python
        box = Rectangle()
        box.width = 200
        ```
    """

    height: float = prop(60, positive_number)
    """How tall the rectangle is. Must be more than 0.

    Example:
        ```python
        box = Rectangle()
        box.height = 120
        ```
    """

    def __init__(
        self,
        x: float = 0,
        y: float = 0,
        *,
        width: float = 100,
        height: float = 60,
        color: str = "steelblue",
        rotation: float = 0,
        title: str = "",
        name: str | None = None,
        visible: bool = True,
        opacity: float = 1,
    ) -> None:
        """Draw a rectangle.

        Args:
            x: Horizontal position of the centre.
            y: Vertical position of the centre.
            width: How wide it is.
            height: How tall it is.
            color: The colour.
            rotation: Turn in degrees, counter-clockwise.
            title: A label drawn on the rectangle.
            name: A secret label for `get(name)`.
            visible: `False` to start hidden.
            opacity: 0 (invisible) to 1 (solid).

        Example:
            ```python
            Rectangle(0, -200, width=120, height=30, color="orange")
            ```
        """
        self._setup(locals())


class Triangle(Shape):
    """A triangle with its point up, centred on `x, y`.

    Example:
        ```python
        roof = Triangle(0, 100, width=120, height=80, color="firebrick")
        ```
    """

    _type = "triangle"

    width: float = prop(100, positive_number)
    """How wide the bottom edge is. Must be more than 0.

    Example:
        ```python
        roof = Triangle()
        roof.width = 160
        ```
    """

    height: float = prop(100, positive_number)
    """How tall the triangle is, from the bottom edge to the point. Must be more than 0.

    Example:
        ```python
        roof = Triangle()
        roof.height = 60
        ```
    """

    def __init__(
        self,
        x: float = 0,
        y: float = 0,
        *,
        width: float = 100,
        height: float = 100,
        color: str = "steelblue",
        rotation: float = 0,
        title: str = "",
        name: str | None = None,
        visible: bool = True,
        opacity: float = 1,
    ) -> None:
        """Draw a triangle.

        Args:
            x: Horizontal position of the centre.
            y: Vertical position of the centre.
            width: How wide the bottom edge is.
            height: How tall it is.
            color: The colour.
            rotation: Turn in degrees, counter-clockwise.
            title: A label drawn on the triangle.
            name: A secret label for `get(name)`.
            visible: `False` to start hidden.
            opacity: 0 (invisible) to 1 (solid).

        Example:
            ```python
            Triangle(0, 0, width=80, height=120, color="purple")
            ```
        """
        self._setup(locals())


class Line(Shape):
    """A straight line from `(x, y)` to `(x2, y2)`. Lines cannot be rotated.

    Example:
        ```python
        Line(-100, -50, 100, 50, width=5, color="crimson")
        ```
    """

    _type = "line"
    _excluded = ("rotation",)

    x2: float = prop(100, number)
    """Horizontal position of the end of the line.

    Example:
        ```python
        line = Line()
        line.x2 = 200
        ```
    """

    y2: float = prop(0, number)
    """Vertical position of the end of the line.

    Example:
        ```python
        line = Line()
        line.y2 = 150
        ```
    """

    width: float = prop(3, positive_number)
    """How thick the line is. Must be more than 0.

    Example:
        ```python
        line = Line()
        line.width = 10
        ```
    """

    color: str = prop("black", colour)
    """The colour of the line, like `"red"` or `"#ff8800"`.

    Example:
        ```python
        line = Line()
        line.color = "crimson"
        ```
    """

    def __init__(
        self,
        x: float = 0,
        y: float = 0,
        x2: float = 100,
        y2: float = 0,
        *,
        width: float = 3,
        color: str = "black",
        title: str = "",
        name: str | None = None,
        visible: bool = True,
        opacity: float = 1,
    ) -> None:
        """Draw a line.

        Args:
            x: Horizontal position of the start.
            y: Vertical position of the start.
            x2: Horizontal position of the end.
            y2: Vertical position of the end.
            width: How thick it is.
            color: The colour.
            title: A label drawn at the middle of the line.
            name: A secret label for `get(name)`.
            visible: `False` to start hidden.
            opacity: 0 (invisible) to 1 (solid).

        Example:
            ```python
            Line(0, 0, 150, 100, width=4, color="teal")
            ```
        """
        self._setup(locals())


class Text(Shape):
    """Words (or emoji) centred on `x, y`. `Text("Hello", 0, 100)`.

    Example:
        ```python
        score = Text("Score: 0", 0, 250, size=40, color="white")
        ```
    """

    _type = "text"
    _excluded = ("title",)

    text: str = prop("", to_text)
    """What the text says. Anything you give is turned into text with `str()`.

    Example:
        ```python
        score = Text("Score: 0")
        score.text = "Score: 10"
        ```
    """

    size: float = prop(32, positive_number)
    """How big the letters are. Must be more than 0.

    Example:
        ```python
        label = Text("Hi")
        label.size = 64
        ```
    """

    color: str = prop("black", colour)
    """The colour of the letters, like `"red"` or `"#ff8800"`.

    Example:
        ```python
        label = Text("Hi")
        label.color = "navy"
        ```
    """

    def __init__(
        self,
        text: str = "",
        x: float = 0,
        y: float = 0,
        *,
        size: float = 32,
        color: str = "black",
        rotation: float = 0,
        name: str | None = None,
        visible: bool = True,
        opacity: float = 1,
    ) -> None:
        """Write some text.

        Args:
            text: What it says. Anything is turned into text with `str()`.
            x: Horizontal position of the centre.
            y: Vertical position of the centre.
            size: How big the letters are.
            color: The colour of the letters.
            rotation: Turn in degrees, counter-clockwise.
            name: A secret label for `get(name)`.
            visible: `False` to start hidden.
            opacity: 0 (invisible) to 1 (solid).

        Example:
            ```python
            Text("Hello!", 0, 0, size=60, color="purple")
            ```
        """
        if isinstance(text, (int, float)) and isinstance(x, str) != isinstance(y, str):
            words, numbers = (x, [text, y]) if isinstance(x, str) else (y, [text, x])
            shown = ", ".join([f'"{words}"', *(repr(value) for value in numbers)])
            raise TypeError(f"Text starts with its words: Text({shown})")
        self._setup(locals())
