from __future__ import annotations

import pytest
from core import _colors, _props


@pytest.mark.parametrize(
    "value",
    [
        "red",
        "RebeccaPurple",
        "transparent",
        "  steelblue ",
        "#abc",
        "#ABCD",
        "#ff8800",
        "#ff880080",
        "rgb(255, 0, 0)",
        "rgb(100%, 0%, 0%)",
        "rgba(255,0,0,0.5)",
        "rgb(255 0 0 / 50%)",
        "hsl(120, 50%, 50%)",
        "hsla(120deg, 50%, 50%, .5)",
        "hsl(0.5turn 50% 50%)",
    ],
)
def test_valid_colours(value: str) -> None:
    assert _colors.is_color(value)
    assert _props.colour("color", value) == value


@pytest.mark.parametrize(
    "value",
    [
        "",
        "redd",
        "#12",
        "#12345",
        "#gggggg",
        "rgb(1, 2)",
        "rgb(a, b, c)",
        "hsl(1, 2, 3)",
        "rgb(1 2 3",
    ]
    + ["rgb(1, 2, 3, 4, 5)", "red;", 5, None],
)
def test_invalid_colours(value: object) -> None:
    assert not _colors.is_color(value)
    with pytest.raises((TypeError, ValueError)):
        _props.colour("color", value)


def test_there_are_148_named_colours() -> None:
    assert len(_colors.NAMED_COLORS) == 148


def test_colour_messages() -> None:
    with pytest.raises(ValueError, match="Did you mean 'steelblue'"):
        _props.colour("color", "steelblu")
    with pytest.raises(ValueError) as info:
        _props.colour("color", "#12")
    assert "Did you mean" not in str(info.value)
    assert "got '#12'" in str(info.value)
    with pytest.raises(TypeError, match="color must be a color name"):
        _props.colour("color", 5)


def test_number_messages() -> None:
    with pytest.raises(TypeError, match="^x must be a number, but got 'ten'$"):
        _props.number("x", "ten")
    for bad in (True, None, [1]):
        with pytest.raises(TypeError):
            _props.number("x", bad)
    for bad in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(ValueError, match="finite"):
            _props.number("x", bad)
    assert _props.number("x", 3) == 3
    assert _props.number("x", 2.5) == 2.5


def test_positive_and_opacity() -> None:
    with pytest.raises(ValueError, match="^radius must be more than 0, but got -5$"):
        _props.positive_number("radius", -5)
    with pytest.raises(ValueError):
        _props.positive_number("radius", 0)
    with pytest.raises(ValueError, match="^opacity must be between 0 and 1, but got 5$"):
        _props.opacity_value("opacity", 5)
    assert _props.opacity_value("opacity", 0) == 0
    assert _props.opacity_value("opacity", 1) == 1
    with pytest.raises(ValueError, match="0 or more"):
        _props.non_negative_number("seconds", -1)


def test_bool_text_and_choice() -> None:
    with pytest.raises(TypeError, match="visible must be True or False, but got 1"):
        _props.boolean("visible", 1)
    with pytest.raises(TypeError, match="title must be text"):
        _props.text("title", 5)
    with pytest.raises(TypeError, match="name must be text"):
        _props.optional_text("name", 5)
    assert _props.optional_text("name", None) is None
    assert _props.to_text("text", 5) == "5"
    style = _props.choice("solid", "dashed", "dotted")
    assert style("style", "dashed") == "dashed"
    with pytest.raises(ValueError, match="Did you mean 'dashed'"):
        style("style", "dashd")
    with pytest.raises(TypeError):
        style("style", 3)


def test_prop_returns_a_descriptor_with_the_given_default() -> None:
    declared = _props.prop(50, _props.positive_number, sync=False)
    assert declared.default == 50
    assert declared.sync is False


@pytest.mark.parametrize(
    ("typo", "expected"),
    [
        ("rde", "red"),
        ("bleu", "blue"),
        ("grene", "green"),
        ("gren", "green"),
        ("gery", "grey"),
        ("grya", "gray"),
        ("ornage", "orange"),
        ("purpel", "purple"),
        ("steelblu", "steelblue"),
    ],
)
def test_real_typos_get_a_suggestion(typo: str, expected: str) -> None:
    assert _colors.suggest_color(typo) == expected


@pytest.mark.parametrize("wild", ["none", "colour", "banana", "asdf", "#12", "rgb"])
def test_wild_guesses_get_no_suggestion(wild: str) -> None:
    assert _colors.suggest_color(wild) is None
    with pytest.raises(ValueError) as info:
        _props.colour("color", wild)
    assert "Did you mean" not in str(info.value)
