from __future__ import annotations

import ast
import inspect
import re
import textwrap
from pathlib import Path

import core
import pytest
from core import _runtime

BLOCK = re.compile(r"```python\n(.*?)```", re.DOTALL)
MODULES = ["api", "shapes", "guides"]


def _docstrings(tree: ast.AST, prefix: str = "") -> list[tuple[str, str]]:
    """Public docstrings: classes, functions, methods and attribute docstrings."""
    found: list[tuple[str, str]] = []
    body = getattr(tree, "body", [])
    for index, node in enumerate(body):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and (
            not node.name.startswith("_") or node.name == "__init__"
        ):
            label = f"{prefix}{node.name}"
            doc = ast.get_docstring(node, clean=True)
            if doc:
                found.append((label, doc))
            found.extend(_docstrings(node, f"{label}."))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            following = body[index + 1] if index + 1 < len(body) else None
            if (
                isinstance(following, ast.Expr)
                and isinstance(following.value, ast.Constant)
                and isinstance(following.value.value, str)
            ):
                label = f"{prefix}{node.target.id}"
                found.append((label, inspect.cleandoc(following.value.value)))
    return found


def _examples() -> list[tuple[str, str]]:
    examples = []
    for module in MODULES:
        source = Path(inspect.getfile(getattr(core, module))).read_text()
        for label, doc in _docstrings(ast.parse(source)):
            for number, code in enumerate(textwrap.dedent(code) for code in BLOCK.findall(doc)):
                examples.append((f"{module}.{label}#{number}", code))
    return examples


EXAMPLES = _examples()


def test_examples_are_found() -> None:
    labels = [label for label, _ in EXAMPLES]
    assert len(labels) > 50
    for expected in ("shapes.Circle.radius#0", "api.wait#0", "guides.Axis.__init__#0"):
        assert expected in labels


@pytest.mark.parametrize(("label", "code"), EXAMPLES, ids=[label for label, _ in EXAMPLES])
def test_docstring_example_runs(label: str, code: str) -> None:
    compiled = compile(code, label, "exec")
    if "while True" in code:
        return
    scope = core.namespace()
    scope["wait"] = lambda seconds=0: None
    _runtime._null.reset()
    exec(compiled, scope)
