"""CSS colour checking, with friendly "Did you mean ...?" hints."""

from __future__ import annotations

import re
from difflib import get_close_matches

NAMED_COLORS = frozenset(
    """
    aliceblue antiquewhite aqua aquamarine azure beige bisque black blanchedalmond blue
    blueviolet brown burlywood cadetblue chartreuse chocolate coral cornflowerblue cornsilk
    crimson cyan darkblue darkcyan darkgoldenrod darkgray darkgreen darkgrey darkkhaki
    darkmagenta darkolivegreen darkorange darkorchid darkred darksalmon darkseagreen
    darkslateblue darkslategray darkslategrey darkturquoise darkviolet deeppink deepskyblue
    dimgray dimgrey dodgerblue firebrick floralwhite forestgreen fuchsia gainsboro ghostwhite
    gold goldenrod gray green greenyellow grey honeydew hotpink indianred indigo ivory khaki
    lavender lavenderblush lawngreen lemonchiffon lightblue lightcoral lightcyan
    lightgoldenrodyellow lightgray lightgreen lightgrey lightpink lightsalmon lightseagreen
    lightskyblue lightslategray lightslategrey lightsteelblue lightyellow lime limegreen linen
    magenta maroon mediumaquamarine mediumblue mediumorchid mediumpurple mediumseagreen
    mediumslateblue mediumspringgreen mediumturquoise mediumvioletred midnightblue mintcream
    mistyrose moccasin navajowhite navy oldlace olive olivedrab orange orangered orchid
    palegoldenrod palegreen paleturquoise palevioletred papayawhip peachpuff peru pink plum
    powderblue purple rebeccapurple red rosybrown royalblue saddlebrown salmon sandybrown
    seagreen seashell sienna silver skyblue slateblue slategray slategrey snow springgreen
    steelblue tan teal thistle tomato turquoise violet wheat white whitesmoke yellow
    yellowgreen
    """.split()  # noqa: SIM905
)

_ALL_NAMES = sorted(NAMED_COLORS | {"transparent"})
_MIN_SIMILARITY = 0.75

_HEX = re.compile(r"#(?:[0-9a-f]{3}|[0-9a-f]{4}|[0-9a-f]{6}|[0-9a-f]{8})")
_FUNCTION = re.compile(r"(rgba?|hsla?)\(([^()]*)\)")
_NUMBER = r"[+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?"
_NUMBER_OR_PERCENT = re.compile(rf"{_NUMBER}%?")
_PERCENT = re.compile(rf"{_NUMBER}%")
_HUE = re.compile(rf"{_NUMBER}(?:deg|grad|rad|turn)?")


def _split_arguments(body: str) -> list[str] | None:
    if "," in body:
        parts = [part.strip() for part in body.split(",")]
    else:
        parts = body.replace("/", " / ").split()
        if len(parts) == 5 and parts[3] == "/":
            del parts[3]
    if len(parts) not in (3, 4) or not all(parts):
        return None
    return parts


def _function_is_valid(kind: str, body: str) -> bool:
    parts = _split_arguments(body)
    if parts is None:
        return False
    if len(parts) == 4 and not _NUMBER_OR_PERCENT.fullmatch(parts[3]):
        return False
    if kind.startswith("rgb"):
        return all(_NUMBER_OR_PERCENT.fullmatch(part) for part in parts[:3])
    return bool(
        _HUE.fullmatch(parts[0]) and _PERCENT.fullmatch(parts[1]) and _PERCENT.fullmatch(parts[2])
    )


def is_color(value: object) -> bool:
    """Return True if `value` is a CSS colour string we accept."""
    if not isinstance(value, str):
        return False
    text = value.strip().lower()
    if text in NAMED_COLORS or text == "transparent":
        return True
    if _HEX.fullmatch(text):
        return True
    match = _FUNCTION.fullmatch(text)
    return bool(match and _function_is_valid(match.group(1), match.group(2)))


def suggest_color(value: str) -> str | None:
    """Return the closest colour name to a misspelt `value`, or None."""
    text = value.strip().lower()
    if not text.isalpha():
        return None
    letters = sorted(text)
    for name in _ALL_NAMES:
        if sorted(name) == letters:
            return name
    matches = get_close_matches(text, _ALL_NAMES, n=1, cutoff=_MIN_SIMILARITY)
    return matches[0] if matches else None
