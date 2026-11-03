import http.client
import os
import signal
import socket
import subprocess
import sys
import threading
from pathlib import Path

import core
import pytest
from core import __main__ as cli
from host_helpers import SSEClient, free_port, pid_alive, wait_until

LIB = str(Path(core.__file__).resolve().parent.parent)
HAS_RUNTIME = hasattr(core, "namespace")


class Cli:
    """``python -m core ...`` as a subprocess whose output is collected on threads."""

    def __init__(self, tmp_path: Path, *args: str, code: str | None = None) -> None:
        command = [sys.executable, "-u"]
        command += ["-c", code, *args] if code else ["-m", "core", *args]
        env = dict(os.environ, PYTHONPATH=LIB, PYTHONDONTWRITEBYTECODE="1")
        self.process = subprocess.Popen(
            command,
            cwd=tmp_path,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.lines: list[str] = []
        self.errors: list[str] = []
        for stream, target in (
            (self.process.stdout, self.lines),
            (self.process.stderr, self.errors),
        ):
            threading.Thread(target=self._collect, args=(stream, target), daemon=True).start()

    @staticmethod
    def _collect(stream, target: list[str]) -> None:
        for line in stream:
            target.append(line.rstrip("\n"))

    @property
    def port(self) -> int:
        wait_until(lambda: bool(self.lines), what="the startup line")
        return int(self.lines[0].split("http://127.0.0.1:")[1].split()[0])

    def stop(self, sig: int = signal.SIGINT) -> int:
        self.process.send_signal(sig)
        return self.process.wait(timeout=10)

    def close(self) -> None:
        if self.process.poll() is None:
            self.process.kill()
        self.process.wait()
        for pipe in (self.process.stdout, self.process.stderr):
            if pipe:
                pipe.close()


@pytest.fixture
def cli_run(tmp_path):
    made: list[Cli] = []

    def start(*args: str, **kwargs) -> Cli:
        instance = Cli(tmp_path, *args, **kwargs)
        made.append(instance)
        return instance

    yield start
    for instance in made:
        instance.close()


def test_no_script_gives_a_friendly_message_and_code_2(cli_run):
    run = cli_run()
    assert run.process.wait(10) == 2
    wait_until(lambda: bool(run.errors), what="message")
    assert "Please tell me which file to run" in run.errors[0]


def test_missing_script(cli_run):
    run = cli_run("nothing.py", "--no-browser")
    assert run.process.wait(10) == 2
    wait_until(lambda: bool(run.errors), what="message")
    assert run.errors == [
        "I can't find the file 'nothing.py'. Check the name and the folder, then try again."
    ]
    assert not any("Traceback" in line for line in run.errors)


def test_folder_instead_of_script(cli_run, tmp_path):
    (tmp_path / "folder").mkdir()
    run = cli_run("folder")
    assert run.process.wait(10) == 2
    wait_until(lambda: bool(run.errors), what="message")
    assert "is a folder" in run.errors[0]


@pytest.mark.skipif(os.name == "nt" or os.geteuid() == 0, reason="needs file permissions")
def test_unreadable_script(cli_run, tmp_path):
    script = tmp_path / "secret.py"
    script.write_text("pass\n")
    script.chmod(0)
    try:
        run = cli_run("secret.py")
        assert run.process.wait(10) == 2
        wait_until(lambda: bool(run.errors), what="message")
        assert "can't read" in run.errors[0]
    finally:
        script.chmod(0o644)


def test_port_out_of_range(cli_run, tmp_path):
    (tmp_path / "main.py").write_text("pass\n")
    run = cli_run("main.py", "--port", "99999")
    assert run.process.wait(10) == 2


def test_exact_port_that_is_busy_fails_with_a_friendly_message(cli_run, tmp_path):
    (tmp_path / "main.py").write_text("pass\n")
    with socket.socket() as blocker:
        blocker.bind(("127.0.0.1", 0))
        blocker.listen()
        busy = blocker.getsockname()[1]
        run = cli_run("main.py", "--no-browser", "--port", str(busy))
        assert run.process.wait(10) == 1
    wait_until(lambda: bool(run.errors), what="message")
    assert run.errors[0].startswith(f"Port {busy} is already in use.")
    assert "--port" in run.errors[0]
    assert not any("Traceback" in line for line in run.errors)


def test_default_port_falls_back_to_the_next_ports(cli_run, tmp_path):
    (tmp_path / "main.py").write_text("pass\n")
    with socket.socket() as blocker:
        blocker.bind(("127.0.0.1", 0))
        blocker.listen()
        busy = blocker.getsockname()[1]
        code = (
            "import sys, core.__main__ as m\n"
            f"m.DEFAULT_PORT = {busy}\n"
            "sys.exit(m.main(['main.py', '--no-browser']))\n"
        )
        run = cli_run(code=code)
        port = run.port
        assert busy < port <= busy + 20
        assert run.stop() == 0


def test_no_free_port_in_the_range(cli_run, tmp_path):
    (tmp_path / "main.py").write_text("pass\n")
    first = free_port()
    blockers = []
    try:
        for offset in range(3):
            sock = socket.socket()
            try:
                sock.bind(("127.0.0.1", first + offset))
            except OSError:
                sock.close()
                pytest.skip("could not reserve consecutive ports")
            sock.listen()
            blockers.append(sock)
        code = (
            "import sys, core.__main__ as m\n"
            f"m.DEFAULT_PORT = {first}\n"
            "m.PORT_TRIES = 2\n"
            "sys.exit(m.main(['main.py', '--no-browser']))\n"
        )
        run = cli_run(code=code)
        assert run.process.wait(10) == 1
        wait_until(lambda: bool(run.errors), what="message")
        assert f"between {first} and {first + 2}" in run.errors[0]
    finally:
        for sock in blockers:
            sock.close()


def test_old_python_gets_a_friendly_message(monkeypatch, capsys):
    monkeypatch.setattr(sys, "version_info", (3, 9, 6, "final", 0))
    assert cli.main(["main.py"]) == 1
    assert "needs Python 3.10 or newer" in capsys.readouterr().err


@pytest.mark.skipif(not HAS_RUNTIME, reason="needs the WP-A runtime")
class TestFullRun:
    def test_startup_lines_status_lines_and_ctrl_c(self, cli_run, tmp_path):
        (tmp_path / "main.py").write_text("print('secret console text')\nCircle()\n")
        run = cli_run("main.py", "--no-browser", "--port", str(free_port()))
        port = run.port
        assert run.lines[0] == (
            f"Python Playground running at http://127.0.0.1:{port}  (Ctrl+C to stop)"
        )
        wait_until(lambda: "Program finished" in run.lines, what="Program finished")
        assert run.lines[1] == "Watching main.py"
        assert not any("secret console text" in line for line in run.lines)

        client = SSEClient(port)
        try:
            snapshot = client.next_message()
        finally:
            client.close()
        assert snapshot["state"] == "finished"
        assert snapshot["console"] == [{"text": "secret console text\n", "stream": "stdout"}]
        assert [o["type"] for o in snapshot["objects"]] == ["circle"]

        assert run.stop() == 0
        assert run.errors == []

    def test_error_line(self, cli_run, tmp_path):
        (tmp_path / "main.py").write_text("x = 1\nprint(nope_nope)\n")
        run = cli_run("main.py", "--no-browser", "--port", str(free_port()))
        wait_until(
            lambda: any(line.startswith("Program stopped by an error") for line in run.lines),
            what="error line",
        )
        error_line = next(line for line in run.lines if line.startswith("Program stopped"))
        assert error_line.startswith(
            "Program stopped by an error: NameError: name 'nope_nope' is not defined"
        )
        assert error_line.endswith("(main.py, line 2)")
        assert run.stop() == 0

    def test_saving_restarts_and_says_so(self, cli_run, tmp_path):
        script = tmp_path / "main.py"
        script.write_text("pass\n")
        run = cli_run("main.py", "--no-browser", "--port", str(free_port()))
        wait_until(lambda: "Program finished" in run.lines, what="first finish")
        script.write_text("print('again')\n")
        wait_until(lambda: run.lines.count("Program finished") == 2, what="second finish")
        assert "main.py changed - restarting" in run.lines
        assert run.stop() == 0

    def test_ctrl_c_stops_the_child_and_frees_the_port(self, cli_run, tmp_path):
        (tmp_path / "main.py").write_text(
            "import os\nprint(os.getpid())\nwhile True:\n    wait(0.1)\n"
        )
        run = cli_run("main.py", "--no-browser", "--port", str(free_port()))
        port = run.port
        client = SSEClient(port)
        try:
            # A slow client connects after the script printed: the line is then in the snapshot.
            messages = client.read_until(lambda m: m["t"] == "print" or bool(m.get("console")))
        finally:
            client.close()
        last = messages[-1]
        pid = int(last["text"] if last["t"] == "print" else last["console"][-1]["text"])
        assert run.stop() == 0
        assert not pid_alive(pid)
        assert run.errors == []
        with socket.socket() as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("127.0.0.1", port))

    def test_sigterm_also_exits_cleanly(self, cli_run, tmp_path):
        (tmp_path / "main.py").write_text("while True:\n    wait(0.1)\n")
        run = cli_run("main.py", "--no-browser", "--port", str(free_port()))
        assert run.port
        assert run.stop(signal.SIGTERM) == 0
        assert run.errors == []

    def test_page_is_served(self, cli_run, tmp_path):
        (tmp_path / "main.py").write_text("pass\n")
        run = cli_run("main.py", "--no-browser", "--port", str(free_port()))
        conn = http.client.HTTPConnection("127.0.0.1", run.port, timeout=5)
        try:
            conn.request("GET", "/static/does-not-exist")
            assert conn.getresponse().status == 404
        finally:
            conn.close()
        assert run.stop() == 0
