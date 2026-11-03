"""Tests for the student-facing shell scripts: run.sh and install.sh."""

from __future__ import annotations

import json
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
TOOLS = ("cat", "cp", "ls", "mkdir", "readlink", "uname")

FAKE_MAIN = """\
import os, sys
import random
print("ARGS", sys.argv[1:])
print("PYTHONPATH", os.environ["PYTHONPATH"])
print("PROG", os.environ.get("PLAYGROUND_PROG"))
print("RANDOM", random.__file__)
print("PATH0", sys.path[:1])
"""

OLD_PYTHON = """\
#!/bin/sh
case "$*" in
    *print*) echo 3.8 ;;
    *) exit 1 ;;
esac
"""


def _executable(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def _tool_bin(tmp_path: Path, name: str = "bin") -> Path:
    """A PATH folder holding only the basic tools the scripts use (and no python)."""
    bin_dir = tmp_path / name
    bin_dir.mkdir()
    for tool in TOOLS:
        found = shutil.which(tool)
        if found:
            (bin_dir / tool).symlink_to(found)
    return bin_dir


def _real_python_bin(tmp_path: Path) -> Path:
    bin_dir = _tool_bin(tmp_path, "pybin")
    _executable(bin_dir / "python3", f'#!/bin/sh\nexec "{sys.executable}" "$@"\n')
    return bin_dir


def _make_root(tmp_path: Path, *, typings: bool = True) -> Path:
    """A copy of the repo's scripts with a tiny fake `core` package."""
    root = tmp_path / "playground"
    root.mkdir()
    for script in ("run.sh", "install.sh"):
        shutil.copy(REPO / script, root / script)
        (root / script).chmod(0o755)
    _executable(root / "engine/lib/core/__main__.py", FAKE_MAIN)
    (root / "engine/lib/core/__init__.py").write_text("")
    if typings:
        (root / "engine/typings").mkdir(parents=True)
        (root / "engine/typings/__builtins__.pyi").write_text("class Circle: ...\n")
    return root


def _sh(
    script: Path, *args: str, path: Path, cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/bin/sh", str(script), *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        env={"PATH": str(path), "HOME": str(script.parent)},
        timeout=30,
    )


def test_scripts_are_executable_and_parse() -> None:
    for name in ("run.sh", "install.sh"):
        script = REPO / name
        assert script.stat().st_mode & stat.S_IXUSR
        assert script.read_text().startswith("#!/bin/sh\n")
        assert subprocess.run(["/bin/sh", "-n", str(script)]).returncode == 0


@pytest.mark.parametrize("args", [(), ("--help",), ("-h",)])
def test_usage(tmp_path: Path, args: tuple[str, ...]) -> None:
    root = _make_root(tmp_path)
    result = _sh(root / "run.sh", *args, path=_tool_bin(tmp_path))
    assert result.returncode == 0
    assert "Usage:" in result.stdout
    assert "new <folder>" in result.stdout
    assert "--port N" in result.stdout
    assert "no examples found" in result.stdout


def test_usage_lists_examples(tmp_path: Path) -> None:
    root = _make_root(tmp_path)
    (root / "examples/solar-system").mkdir(parents=True)
    (root / "examples/solar-system/main.py").write_text("")
    (root / "examples/not-an-example").mkdir()
    result = _sh(root / "run.sh", path=_tool_bin(tmp_path), cwd=root)
    assert "examples/solar-system/main.py" in result.stdout
    assert "not-an-example" not in result.stdout


def test_run_forwards_arguments_and_sets_pythonpath(tmp_path: Path) -> None:
    root = _make_root(tmp_path)
    result = _sh(
        root / "run.sh",
        "main.py",
        "--port",
        "1234",
        "--no-browser",
        path=_real_python_bin(tmp_path),
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert "ARGS ['main.py', '--port', '1234', '--no-browser']" in result.stdout
    assert f"PYTHONPATH {root.resolve()}/engine/lib" in result.stdout


def test_run_works_through_a_symlink_from_another_directory(tmp_path: Path) -> None:
    root = _make_root(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    link = elsewhere / "play"
    link.symlink_to(root / "run.sh")
    result = _sh(link, "main.py", path=_real_python_bin(tmp_path), cwd=elsewhere)
    assert result.returncode == 0, result.stderr
    assert f"PYTHONPATH {root.resolve()}/engine/lib" in result.stdout


def test_run_with_too_old_python(tmp_path: Path) -> None:
    root = _make_root(tmp_path)
    bin_dir = _tool_bin(tmp_path)
    _executable(bin_dir / "python3", OLD_PYTHON)
    result = _sh(root / "run.sh", "main.py", path=bin_dir)
    assert result.returncode == 1
    assert "3.10" in result.stderr
    assert "version 3.8" in result.stderr
    assert "install.sh" in result.stderr
    assert "Traceback" not in result.stderr


def test_run_without_python(tmp_path: Path) -> None:
    root = _make_root(tmp_path)
    result = _sh(root / "run.sh", "main.py", path=_tool_bin(tmp_path))
    assert result.returncode == 1
    assert "python3 was not found" in result.stderr
    assert "install.sh" in result.stderr


def test_run_without_engine_says_so(tmp_path: Path) -> None:
    root = _make_root(tmp_path)
    (root / "engine/lib/core/__main__.py").unlink()
    result = _sh(root / "run.sh", "main.py", path=_real_python_bin(tmp_path))
    assert result.returncode == 1
    assert "engine" in result.stderr


def test_new_creates_project(tmp_path: Path) -> None:
    root = _make_root(tmp_path)
    work = tmp_path / "work"
    work.mkdir()
    result = _sh(root / "run.sh", "new", "my-program", path=_tool_bin(tmp_path), cwd=work)
    assert result.returncode == 0, result.stderr
    project = work / "my-program"
    assert "my-program/main.py" in result.stdout

    source = (project / "main.py").read_text()
    compile(source, "main.py", "exec")
    assert "Circle(" in source
    assert "print(" in source
    assert source.lstrip().startswith("#")

    config = json.loads((project / "pyrightconfig.json").read_text())
    assert config["stubPath"] == "typings"
    assert config["reportUndefinedVariable"] == "error"

    settings = json.loads((project / ".vscode/settings.json").read_text())
    assert settings["python.analysis.typeCheckingMode"] == "basic"
    assert settings["python.analysis.stubPath"] == "typings"

    stub = project / "typings/__builtins__.pyi"
    assert stub.read_text() == (root / "engine/typings/__builtins__.pyi").read_text()
    assert not stub.is_symlink()


def test_new_without_stub_warns_but_succeeds(tmp_path: Path) -> None:
    root = _make_root(tmp_path, typings=False)
    result = _sh(root / "run.sh", "new", "p", path=_tool_bin(tmp_path), cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert "Warning" in result.stderr
    assert (tmp_path / "p/main.py").is_file()
    assert not (tmp_path / "p/typings").exists()


def test_new_accepts_an_empty_existing_folder(tmp_path: Path) -> None:
    root = _make_root(tmp_path)
    (tmp_path / "empty").mkdir()
    result = _sh(root / "run.sh", "new", "empty", path=_tool_bin(tmp_path), cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "empty/main.py").is_file()


def test_new_refuses_non_empty_folder(tmp_path: Path) -> None:
    root = _make_root(tmp_path)
    taken = tmp_path / "taken"
    taken.mkdir()
    (taken / "main.py").write_text("print('mine')\n")
    result = _sh(root / "run.sh", "new", "taken", path=_tool_bin(tmp_path), cwd=tmp_path)
    assert result.returncode == 1
    assert "already has files" in result.stderr
    assert (taken / "main.py").read_text() == "print('mine')\n"
    assert sorted(p.name for p in taken.iterdir()) == ["main.py"]


def test_new_refuses_existing_file(tmp_path: Path) -> None:
    root = _make_root(tmp_path)
    (tmp_path / "afile").write_text("x")
    result = _sh(root / "run.sh", "new", "afile", path=_tool_bin(tmp_path), cwd=tmp_path)
    assert result.returncode == 1
    assert "not a folder" in result.stderr


def test_new_needs_a_folder_name(tmp_path: Path) -> None:
    root = _make_root(tmp_path)
    result = _sh(root / "run.sh", "new", path=_tool_bin(tmp_path), cwd=tmp_path)
    assert result.returncode == 2
    assert "folder name" in result.stderr


def test_install_ok(tmp_path: Path) -> None:
    root = _make_root(tmp_path)
    result = _sh(root / "install.sh", path=_real_python_bin(tmp_path))
    assert result.returncode == 0, result.stderr
    assert "ok: Python 3." in result.stdout
    assert "You are ready" in result.stdout
    assert not any(p.name == "venv" for p in root.iterdir())


def test_install_without_python(tmp_path: Path) -> None:
    root = _make_root(tmp_path)
    result = _sh(root / "install.sh", path=_tool_bin(tmp_path))
    assert result.returncode == 1
    assert "missing: Python 3.10" in result.stdout
    assert "python3 was not found" in result.stdout


def test_install_with_old_python(tmp_path: Path) -> None:
    root = _make_root(tmp_path)
    bin_dir = _tool_bin(tmp_path)
    _executable(bin_dir / "python3", OLD_PYTHON)
    result = _sh(root / "install.sh", path=bin_dir)
    assert result.returncode == 1
    assert "found python3 3.8" in result.stdout


def test_run_tells_the_engine_how_it_was_started(tmp_path: Path) -> None:
    root = _make_root(tmp_path)
    result = _sh(root / "run.sh", "main.py", path=_real_python_bin(tmp_path), cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert f"PROG {root / 'run.sh'}" in result.stdout


def test_a_file_named_like_a_python_module_cannot_get_in_the_way(tmp_path: Path) -> None:
    root = _make_root(tmp_path)
    work = tmp_path / "work"
    work.mkdir()
    (work / "random.py").write_text("raise SystemExit('the student random.py was imported')\n")
    result = _sh(root / "run.sh", "main.py", path=_real_python_bin(tmp_path), cwd=work)
    assert result.returncode == 0, result.stderr
    assert "student random.py" not in result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RANDOM"))
    assert str(work) not in line
    assert f"PATH0 ['{work}']" not in result.stdout and "PATH0 ['']" not in result.stdout


def test_new_quotes_the_folder_in_the_next_step(tmp_path: Path) -> None:
    root = _make_root(tmp_path)
    result = _sh(root / "run.sh", "new", "my proj", path=_tool_bin(tmp_path), cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert '"my proj/main.py"' in result.stdout
    assert (tmp_path / "my proj/main.py").is_file()
