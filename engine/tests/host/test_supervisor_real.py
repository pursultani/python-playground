"""The supervisor driving the real runner and runtime (WP-A). Skipped until that exists."""

import core
import pytest
from core.supervisor import Supervisor
from host_helpers import (
    SSEClient,
    console_text,
    pid_alive,
    post_event,
    wait_until,
    write_script,
)

pytestmark = pytest.mark.skipif(
    not hasattr(core, "namespace"), reason="core.namespace() is not available yet"
)


@pytest.fixture
def start(tmp_path):
    created: list[Supervisor] = []

    def factory(source: str) -> Supervisor:
        supervisor = Supervisor(write_script(tmp_path, source), poll_interval=0.05)
        created.append(supervisor)
        supervisor.start()
        return supervisor

    yield factory
    for supervisor in created:
        supervisor.stop()


def test_drawing_reaches_the_snapshot(start):
    supervisor = start("canvas('navy')\nCircle(x=5, color='red', name='ball')\nprint('hi')\n")
    supervisor.wait_for_state("finished")
    snapshot = supervisor.snapshot()
    assert snapshot["background"] == "navy"
    (circle,) = snapshot["objects"]
    assert circle["type"] == "circle" and circle["props"]["color"] == "red"
    assert "name" not in circle["props"]
    assert console_text(supervisor) == "hi\n"


def test_click_and_key_events_make_the_round_trip(start):
    source = (
        "def clicked(x, y):\n"
        "    print('clicked', x, y)\n"
        "def pressed(key):\n"
        "    print('pressed', key)\n"
        "on_click(clicked)\n"
        "on_key(pressed)\n"
        "while True:\n"
        "    wait(0.02)\n"
    )
    supervisor = start(source)
    supervisor.wait_for_state("running")
    assert post_event(supervisor.port, {"t": "click", "x": 10, "y": 20, "target": None}) == 204
    assert post_event(supervisor.port, {"t": "key", "key": "ArrowUp"}) == 204
    wait_until(lambda: "pressed ArrowUp" in console_text(supervisor), what="handlers to run")
    assert console_text(supervisor) == "clicked 10 20\npressed ArrowUp\n"


def test_a_friendly_error_from_the_api_reaches_the_browser(start):
    supervisor = start("ball = Circle()\nball.colour = 'red'\n")
    supervisor.wait_for_state("crashed")
    error = supervisor.snapshot()["error"]
    assert error["kind"] == "AttributeError"
    assert "colour" in error["message"]
    assert [f["file"] for f in error["frames"]] == ["main.py"]
    assert error["frames"][-1]["line"] == 2


def test_error_in_a_handler_crashes_with_the_handler_frame(start):
    source = "def clicked():\n    oops\non_click(clicked)\nwhile True:\n    wait(0.02)\n"
    supervisor = start(source)
    supervisor.wait_for_state("running")
    post_event(supervisor.port, {"t": "click", "x": 0, "y": 0, "target": None})
    supervisor.wait_for_state("crashed")
    frames = supervisor.snapshot()["error"]["frames"]
    assert [f["function"] for f in frames] == ["<module>", "clicked"]


def test_restart_kills_a_busy_loop_and_the_next_run_starts_blank(start):
    supervisor = start("import os\nCircle()\nprint(os.getpid())\nwhile True:\n    pass\n")
    wait_until(lambda: console_text(supervisor).strip().isdigit(), what="child pid")
    pid = int(console_text(supervisor))
    assert len(supervisor.snapshot()["objects"]) == 1
    supervisor.restart()
    assert not pid_alive(pid)
    wait_until(lambda: console_text(supervisor).strip().isdigit(), what="second pid")
    assert int(console_text(supervisor)) != pid
    assert [o["id"] for o in supervisor.snapshot()["objects"]] == [1]


def test_live_stream_carries_frames_in_order(start):
    supervisor = start(
        "import time\nc = Circle()\nwait(0.1)\nc.x = 50\nwait(0.1)\nc.x = 90\nwait(0.1)\n"
    )
    client = SSEClient(supervisor.port)
    try:
        messages = client.read_until(lambda m: m.get("state") == "finished")
    finally:
        client.close()
    frames = [m for m in messages if m["t"] == "frame"]
    assert frames[0]["ops"][0]["op"] == "create"
    xs = [op["props"]["x"] for f in frames for op in f["ops"] if op["op"] == "update"]
    assert xs[-2:] == [50, 90] or xs == [50, 90]
    assert messages[-1] == {"t": "status", "run": 1, "state": "finished"}
