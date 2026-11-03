from __future__ import annotations

import inspect
from typing import Any

import core
import pytest
from core import Axis, Circle, Grid, Line, Rectangle, Shape, Text, Triangle, get
from core._runtime import Runtime

from .conftest import Recorder

CONCRETE: list[type] = [Circle, Rectangle, Triangle, Line, Text, Grid, Axis]


def pending(runtime: Runtime) -> list[dict[str, Any]]:
    return runtime.scene.peek()


def test_all_and_namespace() -> None:
    assert core.__all__ == [
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
    namespace = core.namespace()
    assert list(namespace) == core.__all__
    assert namespace["Circle"] is Circle


def test_create_op_has_all_synced_props_and_no_name(rt: Runtime) -> None:
    Circle(name="ball")
    (op,) = pending(rt)
    assert op == {
        "op": "create",
        "id": 1,
        "type": "circle",
        "props": {
            "x": 0,
            "y": 0,
            "color": "steelblue",
            "rotation": 0,
            "title": "",
            "radius": 50,
            "visible": True,
            "opacity": 1,
        },
    }


def test_defaults_per_class(rt: Runtime) -> None:
    props = {
        type(obj).__name__: pending(rt)[i]["props"]
        for i, obj in enumerate([Rectangle(), Triangle(), Line(), Text(), Grid(), Axis()])
    }
    assert props["Rectangle"]["width"] == 100 and props["Rectangle"]["height"] == 60
    assert props["Triangle"]["height"] == 100
    assert props["Line"] == {
        "x": 0, "y": 0, "color": "black", "x2": 100, "y2": 0, "width": 3,
        "title": "", "visible": True, "opacity": 1,
    }  # fmt: skip
    assert "rotation" not in props["Line"]
    assert props["Text"]["color"] == "black" and props["Text"]["size"] == 32
    assert props["Text"]["text"] == "" and "title" not in props["Text"]
    assert props["Grid"] == {
        "color": "lightgray", "width": 1, "size": 50, "style": "solid",
        "visible": True, "opacity": 1,
    }  # fmt: skip
    assert props["Axis"]["color"] == "gray" and props["Axis"]["width"] == 3
    assert props["Axis"]["labels"] is True


@pytest.mark.parametrize("cls", CONCRETE)
def test_constructor_signature_matches_properties(cls: type) -> None:
    parameters = inspect.signature(cls).parameters
    assert set(parameters) == set(cls._props)  # type: ignore[attr-defined]
    for key, parameter in parameters.items():
        assert parameter.default == cls._props[key].default  # type: ignore[attr-defined]


def test_positional_arguments(rt: Runtime) -> None:
    Circle(100, 50)
    Text("Hi", 1, 2)
    Line(1, 2, 3, 4)
    props = [op["props"] for op in pending(rt)]
    assert (props[0]["x"], props[0]["y"]) == (100, 50)
    assert (props[1]["text"], props[1]["x"], props[1]["y"]) == ("Hi", 1, 2)
    assert [props[2][k] for k in ("x", "y", "x2", "y2")] == [1, 2, 3, 4]
    with pytest.raises(TypeError, match=r"Circle\(\) takes at most 2 values without a name"):
        Circle(1, 2, 3)  # type: ignore[call-arg]
    with pytest.raises(TypeError, match="Grid"):
        Grid(5)  # type: ignore[call-arg]


def test_unknown_constructor_keyword(rt: Runtime) -> None:
    with pytest.raises(
        TypeError, match=r"^Circle\(\) got an unknown property 'colour'. Did you mean 'color'\?$"
    ):
        Circle(colour="red")  # type: ignore[call-arg]
    with pytest.raises(TypeError) as info:
        Circle(zzzzzz=1)  # type: ignore[call-arg]
    assert "Did you mean" not in str(info.value)
    with pytest.raises(TypeError, match="unknown property 'title'"):
        Text(title="no")  # type: ignore[call-arg]
    with pytest.raises(TypeError, match="unknown property 'rotation'"):
        Line(rotation=3)  # type: ignore[call-arg]
    assert pending(rt) == []


def test_failed_construction_uses_no_id_and_no_name(rt: Runtime) -> None:
    with pytest.raises(ValueError):
        Circle(radius=-1, name="ball")
    first = Circle(name="ball")
    assert pending(rt)[0]["id"] == 1
    assert first is get("ball")


def test_reading_returns_what_was_assigned() -> None:
    ball = Circle()
    ball.x = 3
    ball.y = 2.5
    ball.color = "#ABC"
    assert (ball.x, ball.y, ball.color) == (3, 2.5, "#ABC")
    assert type(ball.x) is int
    label = Text()
    label.text = 42  # type: ignore[assignment]
    assert label.text == "42"


def test_assignment_validates_with_friendly_messages() -> None:
    ball = Circle()
    with pytest.raises(TypeError, match="^x must be a number, but got 'ten'$"):
        ball.x = "ten"  # type: ignore[assignment]
    with pytest.raises(ValueError, match="^opacity must be between 0 and 1, but got 5$"):
        ball.opacity = 5
    with pytest.raises(ValueError, match="radius must be more than 0, but got 0"):
        ball.radius = 0
    with pytest.raises(TypeError, match="visible must be True or False"):
        ball.visible = "yes"  # type: ignore[assignment]
    with pytest.raises(TypeError, match="title must be text"):
        ball.title = 5  # type: ignore[assignment]
    with pytest.raises(ValueError, match="style must be one of"):
        Grid(style="wavy")
    assert ball.x == 0 and ball.opacity == 1


def test_assignment_queues_updates_and_coalesces(rt: Runtime) -> None:
    ball = Circle()
    rt.flush()
    ball.x = 10
    ball.x = 20
    ball.y = 5
    assert pending(rt) == [{"op": "update", "id": 1, "props": {"x": 20, "y": 5}}]


def test_unknown_property_on_builtin_class() -> None:
    ball = Circle()
    with pytest.raises(
        AttributeError, match=r"^Circle has no property 'colour'. Did you mean 'color'\?$"
    ):
        ball.colour = "red"  # type: ignore[attr-defined]
    with pytest.raises(AttributeError, match="^Circle has no property 'colour'"):
        ball.colour  # type: ignore[attr-defined]  # noqa: B018
    with pytest.raises(AttributeError) as info:
        ball.qqqqqq = 1  # type: ignore[attr-defined]
    assert str(info.value) == "Circle has no property 'qqqqqq'."
    with pytest.raises(AttributeError):
        ball.show = 3  # type: ignore[method-assign, assignment]


def test_excluded_properties() -> None:
    with pytest.raises(AttributeError, match="Line has no property 'rotation'"):
        Line().rotation = 5  # type: ignore[attr-defined]
    with pytest.raises(AttributeError, match="Text has no property 'title'"):
        Text().title  # type: ignore[attr-defined]  # noqa: B018
    with pytest.raises(AttributeError):
        Grid().x = 1  # type: ignore[attr-defined]
    with pytest.raises(AttributeError):
        Axis().on_click(None)  # type: ignore[attr-defined]


def test_shape_cannot_be_instantiated() -> None:
    with pytest.raises(TypeError, match="Use Circle, Rectangle"):
        Shape()

    class Thing(Shape):
        pass

    with pytest.raises(TypeError, match="Make it a subclass of Circle"):
        Thing()


def test_subclass_rules(rt: Runtime) -> None:
    class Player(Circle):
        def __init__(self) -> None:
            self.early = 1
            super().__init__(x=0, y=-200, color="orange", name="player")
            self.speed = 10
            self._private = True

        def move_left(self) -> None:
            self.x -= self.speed

    player = Player()
    player.move_left()
    assert player.x == -10 and player.early == 1 and player._private
    assert get("player") is player
    player.lives = 3  # type: ignore[attr-defined]
    with pytest.raises(
        AttributeError, match="Player has no property 'colour'. Did you mean 'color'"
    ):
        player.colour = "red"  # type: ignore[attr-defined]
    with pytest.raises(AttributeError, match="Did you mean 'radius'"):
        player.radiu = 2  # type: ignore[attr-defined]
    with pytest.raises(AttributeError, match="'Player' object has no attribute 'nothing'"):
        player.nothing  # type: ignore[attr-defined]  # noqa: B018
    with pytest.raises(AttributeError, match="Did you mean 'color'"):
        player.colr  # type: ignore[attr-defined]  # noqa: B018
    assert repr(player) == "Player(x=-10, y=-200, color='orange', name='player')"


def test_subclass_cannot_use_excluded_property_of_parent() -> None:
    class Wire(Line):
        pass

    with pytest.raises(AttributeError, match="Wire has no property 'rotation'"):
        Wire().rotation = 1  # type: ignore[attr-defined]


def test_subclass_unknown_constructor_keyword() -> None:
    class Star(Text):
        pass

    with pytest.raises(TypeError, match=r"Star\(\) got an unknown property 'speed'"):
        Star(speed=3)  # type: ignore[call-arg]


def test_properties_before_super_init() -> None:
    class Broken(Circle):
        def __init__(self) -> None:
            self.x = 5

    with pytest.raises(RuntimeError, match=r"Call super\(\).__init__\(\) before using properties"):
        Broken()

    class Peeking(Circle):
        def __init__(self) -> None:
            print(self.x)

    with pytest.raises(RuntimeError, match="before using properties"):
        Peeking()

    class Removing(Circle):
        def __init__(self) -> None:
            self.remove()

    with pytest.raises(RuntimeError, match="before using properties"):
        Removing()


def test_names_are_unique_and_freed_on_remove() -> None:
    first = Circle(name="ball")
    with pytest.raises(
        ValueError, match=r"^There is already an object named 'ball'. Names must be different.$"
    ):
        Rectangle(name="ball")
    other = Circle(name="other")
    with pytest.raises(ValueError, match="already an object named 'ball'"):
        other.name = "ball"
    assert other.name == "other"
    other.name = "renamed"
    assert get("renamed") is other
    with pytest.raises(LookupError):
        get("other")
    Circle(name="other")
    first.name = "ball"  # same name again is fine
    first.name = None
    assert first.name is None
    Circle(name="ball")
    first.remove()
    other.remove()
    assert Circle(name="renamed").name == "renamed"


def test_get_messages() -> None:
    Circle(name="ball")
    assert get("ball").name == "ball"
    with pytest.raises(LookupError, match=r"^No object is named 'bal'. Did you mean 'ball'\?$"):
        get("bal")
    with pytest.raises(LookupError) as info:
        get("zzzzzz")
    assert str(info.value) == "No object is named 'zzzzzz'."
    with pytest.raises(TypeError, match="get needs a name"):
        get(5)  # type: ignore[arg-type]


def test_show_hide(rt: Runtime) -> None:
    ball = Circle()
    rt.flush()
    ball.hide()
    assert ball.visible is False
    assert pending(rt)[0]["props"] == {"visible": False}
    ball.show()
    assert ball.visible is True
    assert pending(rt)[0]["props"] == {"visible": True}


def test_remove_ops_and_silent_changes_afterwards(rt: Runtime, sent: Recorder) -> None:
    ball = Circle()
    rt.flush()
    ball.x = 4
    ball.remove()
    ball.remove()
    ball.x = 99
    ball.name = "late"
    ball.show()
    assert pending(rt) == [{"op": "remove", "id": 1}]
    with pytest.raises(LookupError):
        get("late")
    with pytest.raises(ValueError):
        ball.x = float("nan")


def test_create_and_remove_in_one_frame_sends_nothing(rt: Runtime, sent: Recorder) -> None:
    Circle().remove()
    rt.flush()
    assert sent.messages == []


def test_ids_follow_creation_order_across_classes(rt: Runtime) -> None:
    Grid()
    Circle()
    Text()
    assert [op["id"] for op in pending(rt)] == [1, 2, 3]
    assert [op["type"] for op in pending(rt)] == ["grid", "circle", "text"]


def test_repr() -> None:
    assert repr(Circle()) == "Circle(x=0, y=0)"
    assert repr(Circle(5, 6, name="ball")) == "Circle(x=5, y=6, name='ball')"
    assert repr(Circle(radius=10, color="red")) == "Circle(x=0, y=0, color='red', radius=10)"
    assert repr(Text("hi", 1, 2)) == "Text(x=1, y=2, text='hi')"
    assert repr(Line(x2=5, visible=False)) == "Line(x=0, y=0, x2=5, visible=False)"
    assert repr(Grid()) == "Grid()"
    assert repr(Axis(labels=False, name="a")) == "Axis(labels=False, name='a')"


def test_property_defaults_are_valid() -> None:
    for cls in CONCRETE:
        for key, declared in cls._props.items():  # type: ignore[attr-defined]
            declared.validator(key, declared.default)


def test_every_public_member_has_a_docstring() -> None:
    for cls in [*CONCRETE, Shape]:
        assert inspect.getdoc(cls), cls
        for name, member in vars(cls).items():
            if not name.startswith("_") and callable(member):
                assert inspect.getdoc(member), f"{cls.__name__}.{name}"
    for name in core.__all__:
        assert "Example:" in (inspect.getdoc(getattr(core, name)) or ""), name
