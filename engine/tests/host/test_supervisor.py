import json
import os
import signal
import socket
import sys
import time

import pytest
from core.supervisor import PortUnavailable, Supervisor
from host_helpers import (
    SSEClient,
    bump_mtime,
    console_text,
    fake_argv,
    free_port,
    pid_alive,
    post_event,
    request,
    running,
    wait_until,
    write_script,
)

LOOP = "import time\nwhile True:\n    time.sleep(0.05)\n"


@pytest.fixture
def make(tmp_path):
    """Build a supervisor around a fake child for ``source``; stops everything at the end."""
    created: list[Supervisor] = []

    def factory(source: str, **kwargs) -> Supervisor:
        script = write_script(tmp_path, source)
        kwargs.setdefault("poll_interval", 0.05)
        kwargs.setdefault("child_argv", fake_argv)
        supervisor = Supervisor(script, **kwargs)
        created.append(supervisor)
        return supervisor

    yield factory
    for supervisor in created:
        supervisor.stop()


class TestLifecycle:
    def test_finished(self, make):
        supervisor = make("say('hi\\n')\n")
        supervisor.start()
        supervisor.wait_for_state("finished")
        assert console_text(supervisor) == "hi\n"
        assert supervisor.run == 1

    def test_system_exit_is_finished(self, make):
        supervisor = make("say('a')\nraise SystemExit\nsay('b')\n")
        supervisor.start()
        supervisor.wait_for_state("finished")
        assert console_text(supervisor) == "a"

    def test_running_while_the_script_runs(self, make):
        supervisor = make(LOOP)
        supervisor.start()
        supervisor.wait_for_state("running")
        assert supervisor.state == "running"

    def test_uncaught_error_is_crashed_with_payload(self, make):
        supervisor = make("say('before')\nx = 1\nprint(nope)\n")
        supervisor.start()
        supervisor.wait_for_state("crashed")
        snapshot = supervisor.snapshot()
        assert snapshot["error"]["kind"] == "NameError"
        assert snapshot["error"]["frames"][-1]["line"] == 3
        assert console_text(supervisor) == "before"

    def test_syntax_error_sends_error_then_crashed(self, make):
        supervisor = make("print('hi'\n")
        supervisor.start()
        supervisor.wait_for_state("crashed")
        client = SSEClient(supervisor.port)
        try:
            snapshot = client.next_message()
        finally:
            client.close()
        assert snapshot["state"] == "crashed"
        assert snapshot["error"]["kind"] == "SyntaxError"
        assert snapshot["error"]["frames"][0]["line"] == 1

    def test_child_killed_from_outside_is_crashed(self, make):
        supervisor = make("import os\nsay(str(os.getpid()))\n" + LOOP)
        supervisor.start()
        wait_until(lambda: console_text(supervisor).strip().isdigit(), what="child pid")
        pid = int(console_text(supervisor))
        supervisor.wait_for_state("running")
        os.kill(pid, signal.SIGKILL)
        supervisor.wait_for_state("crashed")
        error = supervisor.snapshot()["error"]
        assert error["message"] == "The program stopped unexpectedly"
        assert error["frames"] == []

    def test_child_that_dies_at_startup_is_crashed(self, make):
        supervisor = make("pass\n", child_argv=lambda script: [sys.executable, "-c", "pass"])
        supervisor.start()
        supervisor.wait_for_state("crashed")
        assert supervisor.snapshot()["error"]["message"] == "The program stopped unexpectedly"

    def test_unstartable_child_is_crashed(self, make):
        supervisor = make("pass\n", child_argv=lambda script: ["/no/such/program"])
        supervisor.start()
        supervisor.wait_for_state("crashed")
        assert "could not be started" in supervisor.snapshot()["error"]["message"]

    def test_missing_script_directory_does_not_hang(self, make, tmp_path):
        supervisor = Supervisor(tmp_path / "gone" / "main.py", child_argv=fake_argv)
        try:
            supervisor.start()
            supervisor.wait_for_state("crashed")
        finally:
            supervisor.stop()

    def test_messages_from_an_old_child_are_ignored(self, make):
        supervisor = make("import time\ntime.sleep(0.3)\nsay('late')\n" + LOOP)
        supervisor.start()
        supervisor.wait_for_state("running", run=1)
        supervisor.restart()
        supervisor.wait_for_state("running", run=2)
        time.sleep(0.6)
        assert console_text(supervisor) == "late"  # only run 2's own output


class TestEventsStream:
    def test_snapshot_comes_first_and_describes_the_run(self, make):
        source = (
            "send({'t':'canvas','background':'navy'})\n"
            "send({'t':'frame','ops':[{'op':'create','id':1,'type':'circle','props':{'x':1}},"
            "{'op':'create','id':2,'type':'text','props':{'text':'a'}}]})\n"
            "send({'t':'frame','ops':[{'op':'update','id':1,'props':{'x':5}}]})\n"
            "say('one ')\nsay('two\\n')\nsay('oops', 'stderr')\n" + LOOP
        )
        supervisor = make(source)
        supervisor.start()
        wait_until(lambda: "oops" in console_text(supervisor), what="console output")
        client = SSEClient(supervisor.port)
        try:
            snapshot = client.next_message()
        finally:
            client.close()
        assert snapshot == {
            "t": "snapshot",
            "run": 1,
            "state": "running",
            "script": "main.py",
            "background": "navy",
            "objects": [
                {"id": 1, "type": "circle", "props": {"x": 5}},
                {"id": 2, "type": "text", "props": {"text": "a"}},
            ],
            "console": [
                {"text": "one two\n", "stream": "stdout"},
                {"text": "oops", "stream": "stderr"},
            ],
            "error": None,
        }

    def test_headers(self, make):
        supervisor = make(LOOP)
        supervisor.start()
        client = SSEClient(supervisor.port)
        try:
            assert client.response.status == 200
            assert (client.response.getheader("Content-Type") or "").startswith("text/event-stream")
            assert client.response.getheader("Cache-Control") == "no-store"
        finally:
            client.close()

    def test_message_order_for_one_run(self, make):
        source = (
            "say('hi\\n')\n"
            "send({'t':'frame','ops':[{'op':'create','id':1,'type':'circle','props':{}}]})\n"
            "import time\ntime.sleep(0.2)\n"
        )
        supervisor = make(source)
        supervisor.start()
        supervisor.wait_for_state("finished")
        client = SSEClient(supervisor.port)
        try:
            assert client.next_message()["t"] == "snapshot"
            supervisor.restart()
            messages = client.read_until(
                lambda m: m == {"t": "status", "run": 2, "state": "finished"}
            )
        finally:
            client.close()
        assert [(m["t"], m.get("state")) for m in messages] == [
            ("run", None),
            ("status", "starting"),
            ("status", "running"),
            ("print", None),
            ("frame", None),
            ("status", "finished"),
        ]
        assert messages[0] == {"t": "run", "run": 2}
        assert messages[1] == {"t": "status", "run": 2, "state": "starting"}
        assert messages[3] == {"t": "print", "text": "hi\n", "stream": "stdout"}

    def test_error_comes_before_crashed_status(self, make):
        supervisor = make("say('x')\nraise ValueError('bad')\n")
        client = None
        supervisor.start()
        supervisor.wait_for_state("crashed")
        client = SSEClient(supervisor.port)
        try:
            client.next_message()
            supervisor.restart()
            messages = client.read_until(lambda m: m.get("state") == "crashed")
        finally:
            client.close()
        kinds = [m["t"] for m in messages]
        assert kinds == ["run", "status", "status", "print", "error", "status"]
        assert messages[-2]["message"] == "bad"

    def test_every_connection_gets_its_own_snapshot(self, make):
        supervisor = make(LOOP)
        supervisor.start()
        supervisor.wait_for_state("running")
        first, second = SSEClient(supervisor.port), SSEClient(supervisor.port)
        try:
            assert first.next_message()["t"] == "snapshot"
            assert second.next_message()["t"] == "snapshot"
            wait_until(lambda: supervisor.client_count == 2, what="two clients")
        finally:
            first.close()
            second.close()

    def test_disconnecting_clients_are_forgotten(self, make):
        supervisor = make(LOOP)
        supervisor.start()
        client = SSEClient(supervisor.port)
        client.next_message()
        wait_until(lambda: supervisor.client_count == 1, what="client registered")
        client.close()
        wait_until(lambda: supervisor.client_count == 0, timeout=5, what="client dropped")

    def test_stream_starts_with_a_fast_reconnect_hint(self, make):
        supervisor = make(LOOP)
        supervisor.start()
        client = SSEClient(supervisor.port)
        try:
            assert client.response.readline() == b"retry: 500\n"
            assert client.response.readline() == b"\n"
            assert client.next_message()["t"] == "snapshot"
        finally:
            client.close()

    def test_keep_alive_comments(self, make):
        supervisor = make(LOOP, keepalive_interval=0.3)
        supervisor.start()
        client = SSEClient(supervisor.port)
        try:
            client.next_message()
            line = b""
            while line.strip() != b": keep-alive":
                line = client.response.readline()
                assert line, "stream closed before a keep-alive arrived"
        finally:
            client.close()

    def test_stop_ends_open_streams_and_is_repeatable(self, make):
        supervisor = make(LOOP)
        supervisor.start()
        client = SSEClient(supervisor.port)
        client.next_message()
        started = time.monotonic()
        supervisor.stop()
        supervisor.stop()
        assert time.monotonic() - started < 5
        try:
            assert client.try_next() is None
        finally:
            client.close()

    def test_a_flood_of_output_reaches_late_clients_as_a_capped_snapshot(self, make):
        source = (
            "for i in range(3000):\n    say(f'{i}\\n', 'stdout' if i % 2 else 'stderr')\n" + LOOP
        )
        supervisor = make(source)
        supervisor.start()
        wait_until(lambda: console_text(supervisor).endswith("2999\n"), what="flood")
        assert len(supervisor.snapshot()["console"]) == 2000


class TestInput:
    def test_events_are_forwarded_to_the_child(self, make):
        source = (
            "import json\n"
            "for _ in range(3):\n"
            "    say(json.dumps(read_event(), sort_keys=True) + '\\n')\n"
        )
        supervisor = make(source)
        supervisor.start()
        supervisor.wait_for_state("running")
        assert post_event(supervisor.port, {"t": "click", "x": 12, "y": -40, "target": 3}) == 204
        assert post_event(supervisor.port, {"t": "key", "key": "ArrowLeft"}) == 204
        assert post_event(supervisor.port, {"t": "click", "x": 0, "y": 0, "target": None}) == 204
        supervisor.wait_for_state("finished")
        lines = [json.loads(line) for line in console_text(supervisor).splitlines()]
        assert lines == [
            {"t": "click", "x": 12, "y": -40, "target": 3},
            {"t": "key", "key": "ArrowLeft"},
            {"t": "click", "x": 0, "y": 0, "target": None},
        ]

    def test_invalid_events_are_rejected_and_not_forwarded(self, make):
        supervisor = make("say(repr(read_event()))\n")
        supervisor.start()
        supervisor.wait_for_state("running")
        port = supervisor.port
        assert request(port, "POST", "/event", b"{not json")[0] == 400
        assert request(port, "POST", "/event", b"")[0] == 400
        assert request(port, "POST", "/event", b"[1]")[0] == 400
        assert post_event(port, {"t": "click", "x": "a", "y": 1, "target": None}) == 400
        assert post_event(port, {"t": "dance"}) == 400
        assert request(port, "POST", "/event", b"x" * 70_000)[0] == 400
        assert console_text(supervisor) == ""
        assert post_event(port, {"t": "key", "key": "a"}) == 204
        supervisor.wait_for_state("finished")
        assert json.loads(console_text(supervisor).replace("'", '"')) == {"t": "key", "key": "a"}

    def test_events_after_the_program_ended_are_dropped_with_204(self, make):
        supervisor = make("pass\n")
        supervisor.start()
        supervisor.wait_for_state("finished")
        assert post_event(supervisor.port, {"t": "key", "key": "a"}) == 204

    def test_restart_endpoint_starts_a_new_run(self, make):
        supervisor = make(LOOP)
        supervisor.start()
        supervisor.wait_for_state("running", run=1)
        client = SSEClient(supervisor.port)
        try:
            client.next_message()
            assert request(supervisor.port, "POST", "/restart")[0] == 204
            messages = client.read_until(lambda m: m.get("state") == "running")
        finally:
            client.close()
        assert messages[0] == {"t": "run", "run": 2}
        assert supervisor.run == 2


class TestRestarting:
    def test_changing_the_script_restarts_it(self, make, tmp_path):
        lines: list[str] = []
        supervisor = make("say('version one')\n", log=lines.append)
        supervisor.start()
        supervisor.wait_for_state("finished", run=1)
        script = tmp_path / "main.py"
        script.write_text("say('version two!')\n")
        supervisor.wait_for_state("finished", run=2)
        assert console_text(supervisor) == "version two!"
        assert "main.py changed - restarting" in lines

    def test_touching_the_file_restarts_even_if_the_size_is_the_same(self, make, tmp_path):
        supervisor = make("say('same')\n")
        supervisor.start()
        supervisor.wait_for_state("finished", run=1)
        bump_mtime(tmp_path / "main.py")
        supervisor.wait_for_state("finished", run=2)

    def test_same_mtime_but_different_size_restarts(self, make, tmp_path):
        script = tmp_path / "main.py"
        supervisor = make("say('a')\n")
        supervisor.start()
        supervisor.wait_for_state("finished", run=1)
        stat = script.stat()
        script.write_text("say('abc')\n")
        os.utime(script, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        supervisor.wait_for_state("finished", run=2)

    def test_one_save_causes_one_restart(self, make, tmp_path):
        supervisor = make("say('one')\n")
        supervisor.start()
        supervisor.wait_for_state("finished", run=1)
        script = tmp_path / "main.py"
        for text in ("say('two')\n", "say('three')\n", "say('four!')\n"):
            script.write_text(text)
            time.sleep(0.01)
        supervisor.wait_for_state("finished", run=2)
        time.sleep(0.5)
        assert supervisor.run == 2
        assert console_text(supervisor) == "four!"

    def test_other_python_files_in_the_directory_and_one_level_down_restart(self, make, tmp_path):
        supervisor = make("say('x')\n")
        supervisor.start()
        supervisor.wait_for_state("finished", run=1)
        (tmp_path / "helper.py").write_text("x = 1\n")
        supervisor.wait_for_state("finished", run=2)
        sub = tmp_path / "pkg"
        sub.mkdir()
        (sub / "tool.py").write_text("y = 1\n")
        supervisor.wait_for_state("finished", run=3)
        (sub / "tool.py").write_text("y = 22\n")
        supervisor.wait_for_state("finished", run=4)

    def test_unrelated_files_do_not_restart(self, make, tmp_path):
        supervisor = make("say('x')\n")
        supervisor.start()
        supervisor.wait_for_state("finished", run=1)
        (tmp_path / "notes.txt").write_text("hello")
        deep = tmp_path / "a" / "b"
        deep.mkdir(parents=True)
        (deep / "deep.py").write_text("z = 1\n")
        hidden = tmp_path / ".venv"
        hidden.mkdir()
        (hidden / "x.py").write_text("z = 1\n")
        time.sleep(0.6)
        assert supervisor.run == 1

    def test_a_crashed_program_restarts_when_fixed(self, make, tmp_path):
        supervisor = make("print(oops\n")
        supervisor.start()
        supervisor.wait_for_state("crashed", run=1)
        (tmp_path / "main.py").write_text("say('fixed')\n")
        supervisor.wait_for_state("finished", run=2)
        assert supervisor.snapshot()["error"] is None

    def test_deleting_and_recreating_the_script(self, make, tmp_path):
        supervisor = make("say('a')\n")
        supervisor.start()
        supervisor.wait_for_state("finished", run=1)
        script = tmp_path / "main.py"
        script.unlink()
        supervisor.wait_for_state("crashed")
        script.write_text("say('back')\n")
        wait_until(lambda: supervisor.state == "finished" and supervisor.run >= 2, what="rerun")
        assert console_text(supervisor) == "back"

    def test_restart_kills_an_infinite_loop(self, make):
        source = "import os\nsay(str(os.getpid()))\nwhile True:\n    pass\n"
        supervisor = make(source)
        supervisor.start()
        wait_until(lambda: console_text(supervisor).strip().isdigit(), what="child pid")
        first_pid = int(console_text(supervisor))
        assert pid_alive(first_pid)
        supervisor.restart()
        assert not pid_alive(first_pid)
        wait_until(lambda: console_text(supervisor).strip().isdigit(), what="second pid")
        assert int(console_text(supervisor)) != first_pid
        assert supervisor.run == 2

    def test_restart_kills_a_child_that_ignores_sigterm(self, make):
        source = (
            "import os, signal\n"
            "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
            "say(str(os.getpid()))\n"
            "while True:\n    pass\n"
        )
        supervisor = make(source)
        supervisor.start()
        wait_until(lambda: console_text(supervisor).strip().isdigit(), what="child pid")
        pid = int(console_text(supervisor))
        started = time.monotonic()
        supervisor.restart()
        elapsed = time.monotonic() - started
        assert not pid_alive(pid)
        assert 0.9 < elapsed < 4

    def test_stop_kills_the_child(self, make):
        supervisor = make("import os\nsay(str(os.getpid()))\n" + LOOP)
        supervisor.start()
        wait_until(lambda: console_text(supervisor).strip().isdigit(), what="child pid")
        pid = int(console_text(supervisor))
        supervisor.stop()
        assert not pid_alive(pid)


class TestHttp:
    @pytest.fixture
    def static(self, tmp_path):
        directory = tmp_path / "pages"
        directory.mkdir()
        (directory / "index.html").write_text("<h1>home</h1>")
        (directory / "app.js").write_text("console.log(1)")
        (directory / "style.css").write_text("body{}")
        (directory / "logo.svg").write_text("<svg/>")
        (directory / ".secret").write_text("hidden")
        (tmp_path / "secret.txt").write_text("top secret")
        return directory

    @pytest.fixture
    def server(self, make, static):
        supervisor = make("pass\n", static_dir=static)
        supervisor.start()
        return supervisor

    def test_index_and_static_files(self, server):
        port = server.port
        status, headers, body = request(port, "GET", "/")
        assert (status, body) == (200, b"<h1>home</h1>")
        assert headers["Content-Type"] == "text/html; charset=utf-8"
        assert headers["Cache-Control"] == "no-store"
        status, headers, body = request(port, "GET", "/static/app.js")
        assert (status, body) == (200, b"console.log(1)")
        assert headers["Content-Type"].startswith("text/javascript")
        assert request(port, "GET", "/static/style.css")[1]["Content-Type"].startswith("text/css")
        assert request(port, "GET", "/static/logo.svg")[1]["Content-Type"] == "image/svg+xml"
        assert request(port, "GET", "/static/index.html")[0] == 200
        assert request(port, "GET", "/static/style.css?v=3")[0] == 200

    def test_missing_files_are_404(self, server):
        port = server.port
        for path in ("/nope", "/static/nope.js", "/static/", "/static", "/static/.secret"):
            assert request(port, "GET", path)[0] == 404, path

    def test_favicon_is_quietly_empty(self, server):
        assert request(server.port, "GET", "/favicon.ico")[0] == 204

    @pytest.mark.parametrize(
        "path",
        [
            "/static/../secret.txt",
            "/static/..%2fsecret.txt",
            "/static/%2e%2e/secret.txt",
            "/static/%2e%2e%2fsecret.txt",
            "/static/../../../../../../etc/passwd",
            "/static//etc/passwd",
            "/static/..\\secret.txt",
            "/static/a/../../secret.txt",
            "/static/%00",
        ],
    )
    def test_directory_traversal_is_refused(self, server, path):
        status, _, body = request(server.port, "GET", path)
        assert status == 404
        assert b"secret" not in body and b"root:" not in body

    def test_symlink_pointing_outside_is_refused(self, server, static, tmp_path):
        (static / "link.txt").symlink_to(tmp_path / "secret.txt")
        assert request(server.port, "GET", "/static/link.txt")[0] == 404

    @pytest.mark.parametrize(
        "host",
        [
            "evil.example",
            "evil.example:80",
            "127.0.0.1.evil.com",
            "127.0.0.1@evil.example",
            "evil.example@127.0.0.1",
            "127.0.0.1:80@evil.example",
            "127.0.0.1:abc",
            "127.0.0.1:",
            "127.0.0.1/evil",
            "localhost:1",
            "localhost",
            "[::1]:80",
            "",
        ],
    )
    def test_non_local_or_odd_host_headers_are_refused(self, server, host):
        port = server.port
        assert request(port, "GET", "/", host=host)[0] == 403
        assert request(port, "GET", "/static/app.js", host=host)[0] == 403
        assert request(port, "POST", "/restart", host=host)[0] == 403
        assert request(port, "POST", "/event", b"{}", host=host)[0] == 403
        assert request(port, "GET", "/events", host=host)[0] == 403

    @pytest.mark.parametrize("name", ["127.0.0.1", "localhost", "LOCALHOST", "[::1]"])
    def test_local_host_headers_with_our_port_are_accepted(self, server, name):
        assert request(server.port, "GET", "/", host=f"{name}:{server.port}")[0] == 200

    def test_cross_site_posts_are_refused(self, server):
        port = server.port
        headers = {"Origin": "https://evil.example"}
        assert request(port, "POST", "/restart", headers=headers)[0] == 403
        assert request(port, "POST", "/event", b"{}", headers=headers)[0] == 403
        assert request(port, "POST", "/restart", headers={"Origin": "null"})[0] == 403
        ok = {"Origin": f"http://127.0.0.1:{port}"}
        assert request(port, "POST", "/restart", headers=ok)[0] == 204

    @pytest.mark.parametrize(
        "origin",
        [
            "http://localhost:1",
            "http://localhost",
            "http://127.0.0.1:{port}@evil.example",
            "http://evil.example:{port}",
            "http://127.0.0.1:{port}x",
            "https://127.0.0.1:{port}",
        ],
    )
    def test_posts_from_another_local_port_or_odd_origin_are_refused(self, server, origin):
        headers = {"Origin": origin.format(port=server.port)}
        assert request(server.port, "POST", "/restart", headers=headers)[0] == 403
        assert request(server.port, "POST", "/event", b"{}", headers=headers)[0] == 403

    @pytest.mark.parametrize("name", ["127.0.0.1", "localhost", "[::1]"])
    def test_posts_from_our_own_page_are_accepted(self, server, name):
        headers = {"Origin": f"http://{name}:{server.port}"}
        assert request(server.port, "POST", "/restart", headers=headers)[0] == 204

    def test_html_cannot_be_framed(self, server):
        _, headers, _ = request(server.port, "GET", "/")
        assert headers["X-Frame-Options"] == "DENY"
        assert headers["Content-Security-Policy"] == "frame-ancestors 'none'"

    def test_unknown_routes_and_methods(self, server):
        port = server.port
        assert request(port, "POST", "/nope")[0] == 404
        assert request(port, "GET", "/event")[0] == 404
        assert request(port, "GET", "/restart")[0] == 404
        assert request(port, "PUT", "/")[0] == 501

    def test_no_cors_headers(self, server):
        _, headers, _ = request(
            server.port, "GET", "/", headers={"Origin": f"http://localhost:{server.port}"}
        )
        assert not any(name.lower().startswith("access-control") for name in headers)

    def test_only_listens_on_loopback(self, server):
        assert server._server.server_address[0] == "127.0.0.1"


class TestPorts:
    def test_random_port(self, make):
        supervisor = make("pass\n")
        supervisor.start()
        assert supervisor.port > 0
        assert supervisor.url == f"http://127.0.0.1:{supervisor.port}/"

    def test_busy_port_falls_back_to_the_next_one(self, make):
        with socket.socket() as blocker:
            blocker.bind(("127.0.0.1", 0))
            blocker.listen()
            busy = blocker.getsockname()[1]
            supervisor = make("pass\n", port=busy, port_tries=20)
            supervisor.start()
            assert busy < supervisor.port <= busy + 20

    def test_exact_port_that_is_busy_fails(self, make):
        with socket.socket() as blocker:
            blocker.bind(("127.0.0.1", 0))
            blocker.listen()
            busy = blocker.getsockname()[1]
            supervisor = make("pass\n", port=busy)
            with pytest.raises(PortUnavailable) as info:
                supervisor.start()
            assert (info.value.first, info.value.last) == (busy, busy)

    def test_all_ports_busy_fails(self, make):
        blockers = []
        try:
            first = free_port()
            for offset in range(3):
                sock = socket.socket()
                try:
                    sock.bind(("127.0.0.1", first + offset))
                except OSError:
                    sock.close()
                    pytest.skip("could not reserve three consecutive ports")
                sock.listen()
                blockers.append(sock)
            supervisor = make("pass\n", port=first, port_tries=2)
            with pytest.raises(PortUnavailable) as info:
                supervisor.start()
            assert (info.value.first, info.value.last) == (first, first + 2)
        finally:
            for sock in blockers:
                sock.close()

    def test_programmatic_helper_context_manager(self, make):
        with running(make("say('x')\n")) as supervisor:
            supervisor.wait_for_state("finished")


def test_wait_for_state_times_out_with_a_helpful_message(make):
    supervisor = make(LOOP)
    supervisor.start()
    supervisor.wait_for_state("running")
    with pytest.raises(TimeoutError, match="finished"):
        supervisor.wait_for_state("finished", timeout=0.2)


def test_stop_before_start_is_harmless(make):
    make("pass\n").stop()


def test_stop_right_after_start(make):
    supervisor = make(LOOP)
    supervisor.start()
    supervisor.stop()
