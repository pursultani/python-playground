"""Guides: the grid and axis that help you read positions on the canvas."""

from __future__ import annotations

from ._props import boolean, choice, colour, positive_number, prop
from .shapes import Object


class Grid(Object):
    """A grid of lines drawn behind every shape. It always includes the lines through the middle.

    Guides have no position and cannot be clicked. They appear as soon as you create them.

    Example:
        ```python
        Grid(size=100, style="dashed")
        ```
    """

    _type = "grid"

    color: str = prop("lightgray", colour)
    """The colour of the lines.

    Example:
        ```python
        grid = Grid()
        grid.color = "silver"
        ```
    """

    width: float = prop(1, positive_number)
    """How thick the lines are. Must be more than 0.

    Example:
        ```python
        grid = Grid()
        grid.width = 2
        ```
    """

    size: float = prop(50, positive_number)
    """The distance between lines. Must be more than 0.

    Example:
        ```python
        grid = Grid()
        grid.size = 100
        ```
    """

    style: str = prop("solid", choice("solid", "dashed", "dotted"))
    """The look of the lines: `"solid"`, `"dashed"` or `"dotted"`.

    Example:
        ```python
        grid = Grid()
        grid.style = "dotted"
        ```
    """

    def __init__(
        self,
        *,
        color: str = "lightgray",
        width: float = 1,
        size: float = 50,
        style: str = "solid",
        name: str | None = None,
        visible: bool = True,
        opacity: float = 1,
    ) -> None:
        """Draw a grid.

        Args:
            color: The colour of the lines.
            width: How thick the lines are.
            size: The distance between lines.
            style: `"solid"`, `"dashed"` or `"dotted"`.
            name: A secret label for `get(name)`.
            visible: `False` to start hidden.
            opacity: 0 (invisible) to 1 (solid).

        Example:
            ```python
            Grid(color="gainsboro", size=25)
            ```
        """
        self._setup(locals())


class Axis(Object):
    """The x axis and y axis through the middle, with tick marks and numbers.

    Guides have no position and cannot be clicked. They appear as soon as you create them.

    Example:
        ```python
        Axis(size=100)
        ```
    """

    _type = "axis"

    color: str = prop("gray", colour)
    """The colour of the axis lines.

    Example:
        ```python
        axis = Axis()
        axis.color = "black"
        ```
    """

    width: float = prop(3, positive_number)
    """How thick the axis lines are. Must be more than 0.

    Example:
        ```python
        axis = Axis()
        axis.width = 5
        ```
    """

    size: float = prop(50, positive_number)
    """The distance between tick marks. Must be more than 0.

    Example:
        ```python
        axis = Axis()
        axis.size = 100
        ```
    """

    style: str = prop("solid", choice("solid", "dashed", "dotted"))
    """The look of the axis lines: `"solid"`, `"dashed"` or `"dotted"`.

    Example:
        ```python
        axis = Axis()
        axis.style = "dashed"
        ```
    """

    labels: bool = prop(True, boolean)
    """`True` to show the numbers beside the tick marks.

    Example:
        ```python
        axis = Axis()
        axis.labels = False
        ```
    """

    def __init__(
        self,
        *,
        color: str = "gray",
        width: float = 3,
        size: float = 50,
        style: str = "solid",
        labels: bool = True,
        name: str | None = None,
        visible: bool = True,
        opacity: float = 1,
    ) -> None:
        """Draw the axes.

        Args:
            color: The colour of the axis lines.
            width: How thick the lines are.
            size: The distance between tick marks.
            style: `"solid"`, `"dashed"` or `"dotted"`.
            labels: `True` to show numbers beside the tick marks.
            name: A secret label for `get(name)`.
            visible: `False` to start hidden.
            opacity: 0 (invisible) to 1 (solid).

        Example:
            ```python
            Axis(labels=False)
            ```
        """
        self._setup(locals())
