"""Tests for the editor stub: it is current, complete, and Pyright really uses it."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import core
import pytest

REPO = Path(__file__).resolve().parents[3]


def _load_generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("gen_stubs", REPO / "engine/tools/gen_stubs.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gen_stubs = _load_generator()
COMMITTED = REPO / "engine" / "typings" / "__builtins__.pyi"

SAMPLE = """\
import random
ball = Circle(100, 50, radius=40, color="orange", name="ball")  # ok
box = Rectangle(0, 0, width=80, height=40, rotation=45)  # ok
roof = Triangle(0, 100, width=50, height=70, title="roof")  # ok
pole = Line(0, 0, 100, 100, width=4, color="red")  # ok
words = Text("Hello", 0, 0, size=30, rotation=10)  # ok
grid = Grid(size=100, style="dashed")  # ok
axis = Axis(labels=False)  # ok
canvas(background="black")  # ok
wait(0.1)  # ok
ball.x += 5  # ok
ball.color = "red"  # ok
ball.hide()  # ok
ball.show()  # ok
ball.remove()  # ok
found = get("ball")  # ok
found.anything = 1  # ok
print(ball.radius, words.text, pole.x2)  # ok
random.random()  # ok

class Player(Circle):  # ok
    def __init__(self):  # ok
        super().__init__(x=0, y=-200, color="orange", name="player")  # ok
        self.speed = 10  # ok

def no_args():  # ok
    pass

def one_arg(x):  # ok
    pass

def two_args(x, y):  # ok
    pass

def key_arg(key):  # ok
    pass

on_click(no_args)  # ok
on_click(one_arg)  # ok
on_click(two_args)  # ok
on_click(None)  # ok
on_key(no_args)  # ok
on_key(key_arg)  # ok
ball.on_click(two_args)  # ok
ball.on_click(None)  # ok

Circle(radius="big")  # error: wrong argument type
ball.colour = "red"  # error: typo in a property
print(ball.colour)  # error: typo in a property
Line(0, 0, 10, 10).rotation  # error: lines cannot rotate
Line(0, 0, 10, 10, rotation=5)  # error: lines cannot rotate
Text("hi").title  # error: text has no title
Text("hi", title="x")  # error: text has no title
Grid().x  # error: guides have no position
Axis().on_click(no_args)  # error: guides cannot be clicked
Circle(100, 50, 40)  # error: radius is keyword-only
Circle(raduis=40)  # error: typo in a keyword
ball.x = "left"  # error: wrong value type
ball.sho()  # error: typo in a method
wait("a lot")  # error: wrong argument type
on_click(5)  # error: not a function
print(undefined_name)  # error: undefined name
Callable  # error: helper imports of the stub do not leak
Any  # error: helper imports of the stub do not leak
Object  # error: the hidden base class is not part of the API
"""


def _find(tool: str) -> str | None:
    beside_python = Path(sys.executable).parent / tool
    if beside_python.exists():
        return str(beside_python)
    return shutil.which(tool)


@pytest.fixture(scope="module")
def project(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("stub-project")
    (root / "typings").mkdir()
    (root / "typings" / "__builtins__.pyi").write_text(gen_stubs.generate())
    (root / "pyrightconfig.json").write_text(
        json.dumps({"stubPath": "typings", "reportUndefinedVariable": "error"})
    )
    (root / "main.py").write_text(SAMPLE)
    return root


@pytest.fixture(scope="module")
def diagnostics(project: Path) -> dict[int, str]:
    pyright = _find("pyright")
    if pyright is None:
        pytest.skip("pyright is not installed")
    proc = subprocess.run(
        [pyright, "--outputjson"],
        cwd=project,
        capture_output=True,
        text=True,
        timeout=180,
        env={**os.environ, "NO_COLOR": "1"},
    )
    report = json.loads(proc.stdout)
    return {
        item["range"]["start"]["line"] + 1: item["message"]
        for item in report["generalDiagnostics"]
        if item["severity"] == "error"
    }


def test_stub_is_up_to_date() -> None:
    assert COMMITTED.read_text() == gen_stubs.generate(), "run `make stubs`"


def test_generation_is_deterministic() -> None:
    assert gen_stubs.generate() == gen_stubs.generate()


def test_check_flag_passes_for_committed_stub() -> None:
    assert gen_stubs.main(["--check"]) == 0


def test_check_flag_fails_for_a_stale_stub(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stale = tmp_path / "__builtins__.pyi"
    stale.write_text("class Circle: ...\n")
    monkeypatch.setattr(gen_stubs, "STUB", stale)
    assert gen_stubs.main(["--check"]) == 1
    assert "make stubs" in capsys.readouterr().out
    assert stale.read_text() == "class Circle: ...\n"


def test_every_public_name_is_in_the_stub() -> None:
    stub = gen_stubs.generate()
    for name in core.__all__:
        kind = "class" if isinstance(getattr(core, name), type) else "def"
        assert f"\n{kind} {name}(" in stub or f"\n{kind} {name}:" in stub, name


def test_stub_has_no_private_names() -> None:
    stub = gen_stubs.generate()
    assert "_setup" not in stub
    assert "_excluded" not in stub
    assert "class Object" not in stub


def test_stub_excludes_removed_members() -> None:
    stub = gen_stubs.generate()
    line = stub[stub.index("class Line(") : stub.index("class Text(")]
    text = stub[stub.index("class Text(") : stub.index("class Grid")]
    assert "rotation" not in line.replace("Lines cannot be rotated", "")
    assert "title: str\n" not in text
    assert "rotation: float\n" in text


def test_stub_carries_docstrings_for_hover() -> None:
    stub = gen_stubs.generate()
    assert "Distance from the centre to the edge." in stub
    assert "Pause the program, show the changes" in stub
    assert "Call `handler` when this shape is clicked." in stub
    assert "Find the object that was created with this `name`." in stub
    assert "Example:" in stub


def test_pyright_accepts_good_code_and_flags_mistakes(
    diagnostics: dict[int, str],
) -> None:
    lines = SAMPLE.splitlines()
    wrong = []
    for number, line in enumerate(lines, start=1):
        expect_error = "# error" in line
        if expect_error != (number in diagnostics):
            wrong.append((number, line, diagnostics.get(number)))
    assert not wrong, "\n".join(map(str, wrong))


def test_api_names_resolve(diagnostics: dict[int, str]) -> None:
    messages = " ".join(diagnostics.values())
    for name in core.__all__:
        assert f'"{name}" is not defined' not in messages


def test_undefined_names_are_still_reported(diagnostics: dict[int, str]) -> None:
    assert any('"undefined_name" is not defined' in m for m in diagnostics.values())


def test_wrong_argument_and_typo_messages_are_clear(diagnostics: dict[int, str]) -> None:
    lines = SAMPLE.splitlines()

    def message(text: str) -> str:
        return diagnostics[next(i for i, line in enumerate(lines, 1) if text in line)]

    assert 'parameter "radius"' in message('radius="big"')
    assert 'Cannot assign to attribute "colour"' in message('ball.colour = "red"')
    assert 'Cannot access attribute "rotation"' in message("Line(0, 0, 10, 10).rotation")
    assert 'Cannot access attribute "title"' in message('Text("hi").title')


def _hover(project: Path, line: int, column: int) -> str:
    """Ask Pyright's language server what the editor would show on hover."""
    server = _find("pyright-langserver")
    if server is None:
        pytest.skip("pyright-langserver is not installed")
    uri = (project / "main.py").as_uri()
    proc = subprocess.Popen(
        [server, "--stdio"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        cwd=project,
    )
    assert proc.stdin is not None
    assert proc.stdout is not None

    def send(message: dict) -> None:
        body = json.dumps(message).encode()
        proc.stdin.write(b"Content-Length: %d\r\n\r\n" % len(body) + body)  # type: ignore[union-attr]
        proc.stdin.flush()  # type: ignore[union-attr]

    def receive() -> dict:
        header = b""
        while not header.endswith(b"\r\n\r\n"):
            header += proc.stdout.read(1)  # type: ignore[union-attr]
        length = next(
            int(part.split(b":")[1])
            for part in header.split(b"\r\n")
            if part.lower().startswith(b"content-length")
        )
        return json.loads(proc.stdout.read(length))  # type: ignore[union-attr]

    def request(ident: int, method: str, params: dict) -> dict:
        send({"jsonrpc": "2.0", "id": ident, "method": method, "params": params})
        while True:
            reply = receive()
            if reply.get("id") == ident:
                return reply

    try:
        folder = {"uri": project.as_uri(), "name": "stub-project"}
        request(
            1,
            "initialize",
            {
                "processId": None,
                "rootUri": folder["uri"],
                "capabilities": {},
                "workspaceFolders": [folder],
            },
        )
        send({"jsonrpc": "2.0", "method": "initialized", "params": {}})
        send(
            {
                "jsonrpc": "2.0",
                "method": "textDocument/didOpen",
                "params": {
                    "textDocument": {
                        "uri": uri,
                        "languageId": "python",
                        "version": 1,
                        "text": (project / "main.py").read_text(),
                    }
                },
            }
        )
        reply = request(
            2,
            "textDocument/hover",
            {
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": column},
            },
        )
        return reply["result"]["contents"]["value"]
    finally:
        proc.kill()
        proc.wait()


def test_hover_shows_help_for_functions_classes_and_properties(project: Path) -> None:
    lines = SAMPLE.splitlines()
    wait_line = next(i for i, line in enumerate(lines) if line.startswith("wait(0.1)"))
    circle_line = next(i for i, line in enumerate(lines) if line.startswith("ball = Circle"))
    radius_line = next(i for i, line in enumerate(lines) if line.startswith("print(ball.radius"))
    assert "Pause the program" in _hover(project, wait_line, 1)
    assert "Draw a circle." in _hover(project, circle_line, 9)
    assert "Distance from the centre to the edge." in _hover(project, radius_line, 12)
