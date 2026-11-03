"""Student files must not break the engine: odd file names, bad encodings, leftover processes."""

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import core
import pytest
from core import __main__ as cli
from core import _errors
from core.supervisor import (
    CHILD_BOOT,
    Supervisor,
    _scan_python_files,
    default_child_argv,
    shadowing_warnings,
)
from host_helpers import console_text, pid_alive, wait_until, write_script
from test_runner_real import Child

pytestmark = pytest.mark.skipif(
    not hasattr(core, "namespace"), reason="core.namespace() is not available yet"
)

SHADOWING_NAMES = ["random", "math", "queue", "json", "core", "threading", "traceback", "types"]


@pytest.fixture
def child(tmp_path):
    made: list[Child] = []

    def start(source: str | bytes | None, name: str = "main.py") -> Child:
        instance = Child(tmp_path, source, name)
        made.append(instance)
        return instance

    yield start
    for instance in made:
        instance.close()


@pytest.mark.parametrize("name", SHADOWING_NAMES)
def test_a_sibling_named_like_a_module_does_not_break_the_run(child, tmp_path, name):
    (tmp_path / f"{name}.py").write_text("raise RuntimeError('the student file was imported')\n")
    source = (
        "import json, math, queue, random, sys\n"
        f"import {name} as shadow\n"
        "Circle(radius=5)\n"
        f"print(getattr(shadow, '__file__', '') != {str(tmp_path / (name + '.py'))!r})\n"
    )
    run = child(source)
    assert run.wait() == 0, run.messages[-1:]
    assert run.kinds()[-1] == "end"
    assert run.console() == "True\n"


@pytest.mark.parametrize("name", SHADOWING_NAMES)
def test_a_script_named_like_a_module_still_runs(child, name):
    run = child("import random, json\nCircle()\nprint('ran', random.__name__)\n", f"{name}.py")
    assert run.wait() == 0, run.messages[-1:]
    assert run.console() == "ran random\n"


def test_the_script_folder_is_last_on_the_search_path(child, tmp_path):
    (tmp_path / "helpers.py").write_text("VALUE = 42\n")
    run = child(
        "import sys, helpers\n"
        "print(helpers.VALUE, sys.path[-1], '' in sys.path, sys.path.count(sys.path[-1]))\n"
    )
    assert run.wait() == 0
    assert run.console() == f"42 {tmp_path} False 1\n"


def test_errors_in_a_helper_still_show_frames(child, tmp_path):
    (tmp_path / "helper_file.py").write_text("def boom():\n    return missing_name\n")
    run = child("import helper_file\nhelper_file.boom()\n")
    assert run.wait() == 1
    assert [f["file"] for f in run.messages[-1]["frames"]] == ["main.py", "helper_file.py"]


@pytest.mark.parametrize(
    ("data", "start"),
    [
        ("print('héllo')\n".encode("latin-1"), "main.py isn't saved as UTF-8."),
        ("print('hi')\n".encode("utf-16"), "main.py isn't saved as UTF-8."),
        (b"# coding: nonsense\nprint(1)\n", "main.py isn't saved as UTF-8."),
        (b"print('a')\x00\nprint('b')\n", "main.py has a null byte in it"),
    ],
)
def test_unusable_files_get_a_friendly_message_with_just_the_name(child, tmp_path, data, start):
    run = child(data)
    assert run.wait() == 1
    error = run.messages[-1]
    assert error["t"] == "error" and error["message"].startswith(start)
    assert error["frames"] == [] and error["context"] == []
    assert str(tmp_path) not in json.dumps(error)


@pytest.mark.skipif(os.name == "nt" or os.geteuid() == 0, reason="needs file permissions")
def test_an_unreadable_script_gets_a_friendly_message(child, tmp_path):
    script = tmp_path / "main.py"
    script.write_text("pass\n")
    script.chmod(0)
    try:
        run = child(None)
        assert run.wait() == 1
        assert run.messages[-1]["message"].startswith("I can't read main.py.")
    finally:
        script.chmod(0o644)


class TestSuggestions:
    """The "Did you mean" fallback used on Python 3.10 and 3.11."""

    @staticmethod
    def failure(source: str, namespace: dict | None = None) -> BaseException:
        try:
            exec(compile(source, "<student>", "exec"), namespace if namespace is not None else {})
        except BaseException as exc:
            return exc
        raise AssertionError("no error")

    def test_name_error_suggests_a_global(self):
        exc = self.failure("ball = 1\nprint(bal)\n")
        assert _errors._suggestion(exc, "/nowhere") == "ball"

    def test_name_error_suggests_a_builtin(self):
        assert _errors._suggestion(self.failure("prnt(1)\n"), "/nowhere") == "print"

    def test_name_error_suggests_the_api_names(self):
        exc = self.failure("Circl()\n", core.namespace())
        assert _errors._suggestion(exc, "/nowhere") == "Circle"

    def test_name_error_suggests_a_local(self):
        exc = self.failure("def f():\n    speed = 1\n    return sped\nf()\n")
        assert _errors._suggestion(exc, "/nowhere") == "speed"

    def test_nothing_close_gives_no_suggestion(self):
        assert _errors._suggestion(self.failure("zzzzzz\n"), "/nowhere") is None

    def test_attribute_error_suggests_from_the_object(self):
        class Ball:
            color = "red"
            _secret = 1

        try:
            _ = Ball().colr  # type: ignore[attr-defined]
        except AttributeError as exc:
            assert _errors._suggestion(exc, "/nowhere") == "color"

    def test_attribute_error_does_not_offer_private_names_for_public_typos(self):
        class Ball:
            _secret = 1

        try:
            _ = Ball().secret  # type: ignore[attr-defined]
        except AttributeError as exc:
            assert _errors._suggestion(exc, "/nowhere") is None

    def test_the_suffix_is_added_only_before_python_3_12(self, monkeypatch):
        monkeypatch.setattr(_errors, "_plain_message", lambda exc: "name 'bal' is not defined")
        exc = self.failure("ball = 1\nprint(bal)\n")
        monkeypatch.setattr(_errors.sys, "version_info", (3, 11, 0, "final", 0))
        assert _errors._message(exc, "/nowhere") == (
            "name 'bal' is not defined. Did you mean: 'ball'?"
        )
        monkeypatch.setattr(_errors.sys, "version_info", (3, 12, 0, "final", 0))
        assert _errors._message(exc, "/nowhere") == "name 'bal' is not defined"

    def test_an_existing_suggestion_is_left_alone(self, monkeypatch):
        monkeypatch.setattr(_errors.sys, "version_info", (3, 11, 0, "final", 0))
        monkeypatch.setattr(
            _errors, "_plain_message", lambda exc: "name 'bal' is not defined. Did you mean: 'x'?"
        )
        assert _errors._message(self.failure("bal\n"), "/nowhere").count("Did you mean") == 1

    def test_the_real_runner_reports_a_name_suggestion(self, child):
        run = child("ball = Circle()\nbal.x = 3\n")
        assert run.wait() == 1
        assert run.messages[-1]["message"].endswith("Did you mean: 'ball'?")

    def test_the_real_runner_reports_an_attribute_suggestion(self, child):
        run = child("import math\nmath.sqroot(4)\n")
        assert run.wait() == 1
        assert run.messages[-1]["message"].endswith("Did you mean: 'sqrt'?")


class TestShadowWarnings:
    def test_sibling_files_are_named(self, tmp_path):
        for name in ("random.py", "queue.py", "helpers.py", "test.py", "this.py", "core.py"):
            (tmp_path / name).write_text("")
        warnings = shadowing_warnings(tmp_path, "main.py")
        by_name = {w.split(" ")[0]: w for w in warnings}
        assert set(by_name) == {"core.py", "queue.py", "random.py"}
        assert by_name["random.py"] == (
            "random.py has the same name as a Python module that comes with Python, so "
            "Python's own random can't be used. Rename it, for example my_random.py."
        )

    def test_the_script_itself_gets_its_own_wording(self, tmp_path):
        (tmp_path / "random.py").write_text("")
        (warning,) = shadowing_warnings(tmp_path, "random.py")
        assert warning.startswith("random.py has the same name as a Python module")
        assert "still runs" in warning and "my_random.py" in warning

    def test_nothing_to_warn_about(self, tmp_path):
        (tmp_path / "main.py").write_text("")
        (tmp_path / "helpers.py").write_text("")
        assert shadowing_warnings(tmp_path, "main.py") == []

    def test_the_warning_reaches_the_console_and_the_terminal_once(self, tmp_path):
        (tmp_path / "queue.py").write_text("")
        lines: list[str] = []
        supervisor = Supervisor(
            write_script(tmp_path, "print('hi')\n"), poll_interval=0.05, log=lines.append
        )
        supervisor.start()
        try:
            supervisor.wait_for_state("finished")
            first = supervisor.snapshot()["console"][0]
            assert first["stream"] == "stderr"
            assert first["text"].startswith("Warning: queue.py has the same name")
            assert console_text(supervisor).endswith("hi\n")
            supervisor.restart()
            supervisor.wait_for_state("finished", run=2)
            assert console_text(supervisor).startswith("Warning: queue.py")
            assert sum(line.startswith("Warning: queue.py") for line in lines) == 1
        finally:
            supervisor.stop()

    @pytest.mark.parametrize("name", ["random", "math", "queue", "json", "core"])
    def test_full_stack_with_a_clashing_script(self, tmp_path, name):
        script = write_script(tmp_path, "Circle()\nprint('ok')\n", f"{name}.py")
        supervisor = Supervisor(script, poll_interval=0.05)
        supervisor.start()
        try:
            supervisor.wait_for_state("finished")
            text = console_text(supervisor)
            assert f"Warning: {name}.py has the same name" in text
            assert text.endswith("ok\n")
        finally:
            supervisor.stop()

    @pytest.mark.parametrize("name", ["random", "math", "queue", "json", "core"])
    def test_full_stack_with_a_clashing_sibling(self, tmp_path, name):
        (tmp_path / f"{name}.py").write_text("raise RuntimeError('wrong file')\n")
        script = write_script(tmp_path, "import random, json\nCircle()\nprint('ok')\n")
        supervisor = Supervisor(script, poll_interval=0.05)
        supervisor.start()
        try:
            supervisor.wait_for_state("finished")
            assert f"Warning: {name}.py has the same name" in console_text(supervisor)
            assert console_text(supervisor).endswith("ok\n")
        finally:
            supervisor.stop()


def _running(pid: int) -> bool:
    """Alive and not a zombie."""
    if not pid_alive(pid):
        return False
    try:
        with open(f"/proc/{pid}/stat") as stat:
            return stat.read().rpartition(")")[2].split()[0] != "Z"
    except OSError:
        pass
    state = subprocess.run(
        ["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True
    ).stdout.strip()
    return bool(state) and not state.startswith("Z")


@pytest.mark.skipif(os.name == "nt", reason="process groups are POSIX only")
class TestProcessGroups:
    SPAWN = (
        "import subprocess\n"
        "p = subprocess.Popen(['sleep', '60'])\n"
        "print('PID', p.pid)\n"
        "while True:\n"
        "    wait(0.05)\n"
    )

    @staticmethod
    def grandchild(supervisor: Supervisor) -> int:
        wait_until(lambda: "PID " in console_text(supervisor), what="the grandchild")
        return int(console_text(supervisor).split("PID ")[1].split()[0])

    def test_restart_kills_programs_the_script_started(self, tmp_path):
        supervisor = Supervisor(write_script(tmp_path, self.SPAWN), poll_interval=0.05)
        supervisor.start()
        try:
            pid = self.grandchild(supervisor)
            assert _running(pid)
            supervisor.restart()
            wait_until(lambda: not _running(pid), what="the grandchild to die")
        finally:
            supervisor.stop()

    def test_stop_kills_programs_the_script_started(self, tmp_path):
        supervisor = Supervisor(write_script(tmp_path, self.SPAWN), poll_interval=0.05)
        supervisor.start()
        pid = self.grandchild(supervisor)
        supervisor.stop()
        wait_until(lambda: not _running(pid), what="the grandchild to die")

    def test_a_finished_script_leaves_nothing_behind(self, tmp_path):
        source = "import subprocess\np = subprocess.Popen(['sleep', '60'])\nprint('PID', p.pid)\n"
        supervisor = Supervisor(write_script(tmp_path, source), poll_interval=0.05)
        supervisor.start()
        try:
            supervisor.wait_for_state("finished")
            pid = self.grandchild(supervisor)
            wait_until(lambda: not _running(pid), what="the grandchild to die")
        finally:
            supervisor.stop()


class TestWatcherLimits:
    def test_only_top_level_and_one_level_of_sub_folders(self, tmp_path):
        (tmp_path / "main.py").write_text("")
        (tmp_path / "sub/deeper").mkdir(parents=True)
        (tmp_path / "sub/a.py").write_text("")
        (tmp_path / "sub/deeper/b.py").write_text("")
        names = {os.path.relpath(p, tmp_path) for p in _scan_python_files(tmp_path)}
        assert names == {"main.py", "sub/a.py"}

    @pytest.mark.parametrize(
        "folder", [".git", ".venv", "venv", "env", "node_modules", "__pycache__", "site-packages"]
    )
    def test_noisy_folders_are_skipped(self, tmp_path, folder):
        (tmp_path / folder).mkdir()
        (tmp_path / folder / "x.py").write_text("")
        (tmp_path / "main.py").write_text("")
        assert [os.path.basename(p) for p in _scan_python_files(tmp_path)] == ["main.py"]

    def test_huge_sub_folders_are_skipped(self, tmp_path):
        (tmp_path / "big").mkdir()
        for index in range(250):
            (tmp_path / "big" / f"a{index}.py").write_text("")
        (tmp_path / "small").mkdir()
        (tmp_path / "small" / "ok.py").write_text("")
        found = [os.path.relpath(p, tmp_path) for p in _scan_python_files(tmp_path)]
        assert "small/ok.py" in found
        assert len(found) < 210

    def test_descending_can_be_switched_off(self, tmp_path):
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub/a.py").write_text("")
        (tmp_path / "main.py").write_text("")
        found = _scan_python_files(tmp_path, descend=False)
        assert [os.path.basename(p) for p in found] == ["main.py"]

    def test_home_and_root_are_not_descended_into(self, tmp_path, monkeypatch):
        (tmp_path / "sub").mkdir()
        monkeypatch.setenv("HOME", str(tmp_path))
        assert Supervisor(tmp_path / "main.py")._watch_subdirs is False
        assert Supervisor(tmp_path / "sub" / "main.py")._watch_subdirs is True
        assert Supervisor(Path("/") / "main.py")._watch_subdirs is False

    def test_a_change_in_a_sub_folder_still_restarts(self, tmp_path):
        (tmp_path / "pkg").mkdir()
        helper = tmp_path / "pkg" / "h.py"
        helper.write_text("A = 1\n")
        supervisor = Supervisor(write_script(tmp_path, "print('x')\n"), poll_interval=0.05)
        supervisor.start()
        try:
            supervisor.wait_for_state("finished")
            time.sleep(0.1)
            helper.write_text("A = 22222\n")
            wait_until(lambda: supervisor.run == 2, what="the restart")
        finally:
            supervisor.stop()


class TestCommandLine:
    def test_prog_name_comes_from_the_environment(self, monkeypatch, capsys):
        monkeypatch.setenv("PLAYGROUND_PROG", "./run.sh")
        assert cli.main([]) == 2
        assert "Try:  ./run.sh main.py" in capsys.readouterr().err

    def test_folder_message_uses_the_prog_name(self, monkeypatch, capsys, tmp_path):
        monkeypatch.setenv("PLAYGROUND_PROG", "./run.sh")
        assert cli.main([str(tmp_path)]) == 2
        assert "./run.sh main.py" in capsys.readouterr().err

    def test_default_prog_name(self, monkeypatch, capsys):
        monkeypatch.delenv("PLAYGROUND_PROG", raising=False)
        assert cli.main([]) == 2
        assert "Try:  python -m core main.py" in capsys.readouterr().err

    def test_help_uses_the_prog_name(self, monkeypatch, capsys):
        monkeypatch.setenv("PLAYGROUND_PROG", "./run.sh")
        with pytest.raises(SystemExit):
            cli.main(["--help"])
        assert "usage: ./run.sh" in capsys.readouterr().out

    @pytest.mark.parametrize("error", [KeyboardInterrupt, SystemExit])
    def test_an_interrupt_during_startup_exits_quietly_and_cleans_up(
        self, monkeypatch, tmp_path, capsys, error
    ):
        stopped: list[bool] = []

        def start(self: Supervisor) -> None:
            raise error

        monkeypatch.setattr(Supervisor, "start", start)
        monkeypatch.setattr(Supervisor, "stop", lambda self: stopped.append(True))
        script = write_script(tmp_path, "pass\n")
        assert cli.main([str(script), "--no-browser"]) == 0
        assert stopped == [True]
        assert "Traceback" not in capsys.readouterr().err

    def test_the_sigterm_handler_is_installed_before_start(self, monkeypatch, tmp_path):
        seen: list[object] = []

        def start(self: Supervisor) -> None:
            seen.append(signal.getsignal(signal.SIGTERM))
            raise KeyboardInterrupt

        monkeypatch.setattr(Supervisor, "start", start)
        before = signal.getsignal(signal.SIGTERM)
        cli.main([str(write_script(tmp_path, "pass\n")), "--no-browser"])
        assert seen == [cli._raise_exit]
        assert signal.getsignal(signal.SIGTERM) == before


def test_the_child_is_started_with_the_boot_code():
    argv = default_child_argv("/x/main.py")
    assert argv[0] == sys.executable
    assert argv[-2:] == [CHILD_BOOT, "/x/main.py"]
    assert "\n" not in CHILD_BOOT
