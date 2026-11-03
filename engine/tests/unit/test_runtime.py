from __future__ import annotations

import sys
import threading
import time
from typing import Any

import pytest
from core import Circle, Rectangle, canvas, get, on_click, on_key, wait
from core import _runtime as runtime_module
from core._runtime import Runtime, current

from .conftest import Recorder


def click(x: int = 0, y: int = 0, target: int | None = None) -> dict[str, Any]:
    return {"t": "click", "x": x, "y": y, "target": target}


def key(name: str) -> dict[str, Any]:
    return {"t": "key", "key": name}


def wait_until(condition: Any, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.005)


def test_null_runtime_records_without_sending() -> None:
    assert current() is runtime_module._null
    Circle()
    canvas("black")
    assert [op["op"] for op in current().scene.peek()] == ["create"]
    current().flush()
    assert len(current().scene.peek()) == 1


def test_flush_emits_canvas_frame_and_print_only_when_non_empty(
    rt: Runtime, sent: Recorder
) -> None:
    rt.flush()
    assert sent.messages == []
    Circle()
    canvas("navy")
    rt.print_stream("stdout").write("hi\n")
    rt.flush()
    assert [m["t"] for m in sent.messages] == ["canvas", "frame", "print"]
    assert sent.of("canvas")[0]["background"] == "navy"
    assert sent.of("frame")[0]["ops"][0]["op"] == "create"
    assert sent.of("print")[0] == {"t": "print", "text": "hi\n", "stream": "stdout"}
    rt.flush()
    assert len(sent.messages) == 3


def test_canvas_validates_and_keeps_shapes(rt: Runtime, sent: Recorder) -> None:
    Circle()
    canvas()
    canvas("black")
    rt.flush()
    assert sent.of("canvas") == [{"t": "canvas", "background": "black"}]
    assert sent.of("frame")[0]["ops"][0]["op"] == "create"
    with pytest.raises(ValueError, match="background must be a color name"):
        canvas("blak!")
    with pytest.raises(TypeError):
        canvas(5)  # type: ignore[arg-type]
    assert canvas("red") is None


def test_print_chunks_coalesce_per_stream_in_order(rt: Runtime, sent: Recorder) -> None:
    out, err = rt.print_stream("stdout"), rt.print_stream("stderr")
    out.write("a")
    out.write("b\n")
    err.write("oops")
    out.write("c")
    rt.flush()
    assert [(m["stream"], m["text"]) for m in sent.of("print")] == [
        ("stdout", "ab\n"),
        ("stderr", "oops"),
        ("stdout", "c"),
    ]


def test_a_print_flood_is_capped_per_flush_and_says_so(rt: Runtime, sent: Recorder) -> None:
    out = rt.print_stream("stdout")
    for _ in range(100):
        out.write("x" * 10_000 + "\n")
    rt.flush()
    printed = sent.of("print")
    total = sum(len(m["text"]) for m in printed if m["stream"] == "stdout")
    assert total <= runtime_module.MAX_PRINT_CHARS_PER_FLUSH
    assert printed[-1]["stream"] == "stderr"
    assert "wait(0.1)" in printed[-1]["text"]
    sent.messages.clear()
    out.write("calm\n")
    rt.flush()
    assert [(m["stream"], m["text"]) for m in sent.of("print")] == [("stdout", "calm\n")]


def test_print_cap_notice_starts_on_its_own_line(rt: Runtime, sent: Recorder) -> None:
    rt.print_stream("stdout").write("y" * (runtime_module.MAX_PRINT_CHARS_PER_FLUSH + 5))
    rt.flush()
    assert sent.of("print")[-1]["text"].startswith("\nToo much")


def test_print_stream_behaves_like_a_file(rt: Runtime, sent: Recorder, monkeypatch) -> None:
    stream = rt.print_stream("stdout")
    assert stream.writable() and not stream.isatty() and not stream.closed
    assert stream.write("") == 0
    stream.flush()
    monkeypatch.setattr(sys, "stdout", stream)
    print("hello", 3)
    rt.flush()
    assert sent.of("print")[0]["text"] == "hello 3\n"
    with pytest.raises(TypeError):
        stream.write(b"x")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        rt.print_stream("other")


def test_wait_flushes_immediately_without_sleeping(rt: Runtime, sent: Recorder) -> None:
    Circle()
    started = time.monotonic()
    wait(0)
    assert time.monotonic() - started < 0.1
    assert len(sent.of("frame")) == 1


def test_wait_sleeps_for_the_requested_time(rt: Runtime) -> None:
    started = time.monotonic()
    wait(0.1)
    assert 0.09 <= time.monotonic() - started < 0.5


def test_wait_validates_seconds() -> None:
    with pytest.raises(TypeError, match="seconds must be a number, but got 'x'"):
        wait("x")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="seconds must be 0 or more, but got -1"):
        wait(-1)
    with pytest.raises(TypeError):
        wait(True)


def test_click_goes_to_target_handler_else_canvas_handler(rt: Runtime) -> None:
    calls: list[tuple[str, tuple[Any, ...]]] = []
    ball = Circle()
    box = Rectangle()
    plain = Circle()
    ball.on_click(lambda x, y: calls.append(("ball", (x, y))))
    box.on_click(lambda: calls.append(("box", ())))
    on_click(lambda x, y: calls.append(("canvas", (x, y))))
    rt.feed_event(click(1, 2, target=1))
    rt.feed_event(click(3, 4, target=2))
    rt.feed_event(click(5, 6, target=3))
    rt.feed_event(click(7, 8, target=None))
    rt.feed_event(click(9, 10, target=99))
    wait(0)
    assert calls == [
        ("ball", (1, 2)),
        ("box", ()),
        ("canvas", (5, 6)),
        ("canvas", (7, 8)),
        ("canvas", (9, 10)),
    ]
    assert plain.name is None


def test_click_without_any_handler_is_ignored(rt: Runtime) -> None:
    Circle()
    rt.feed_event(click(1, 2, target=1))
    rt.feed_event(click(1, 2))
    wait(0)


def test_click_coordinates_are_rounded_and_bad_events_ignored(rt: Runtime) -> None:
    seen: list[tuple[int, int]] = []
    on_click(lambda x, y: seen.append((x, y)))
    rt.feed_event(click(1.6, -2.4))  # type: ignore[arg-type]
    rt.feed_event({"t": "click", "x": "a", "y": 1})
    rt.feed_event({"t": "bogus"})
    rt.feed_event("nonsense")  # type: ignore[arg-type]
    wait(0)
    assert seen == [(2, -2)]


def test_key_events_and_arity(rt: Runtime) -> None:
    keys: list[Any] = []
    on_key(keys.append)
    rt.feed_event(key("ArrowLeft"))
    rt.feed_event(key("Space"))
    wait(0)
    assert keys == ["ArrowLeft", "Space"]


@pytest.mark.parametrize(
    ("make", "expected"),
    [
        (lambda log: lambda: log.append(()), ()),
        (lambda log: lambda x: log.append((x,)), (4,)),
        (lambda log: lambda x, y: log.append((x, y)), (4, 5)),
        (lambda log: lambda x, y=0: log.append((x, y)), (4, 5)),
        (lambda log: lambda *args: log.append(args), (4, 5)),
        (lambda log: lambda x, *rest: log.append((x, *rest)), (4, 5)),
    ],
)
def test_click_handler_arity(rt: Runtime, make: Any, expected: tuple[int, ...]) -> None:
    log: list[tuple[int, ...]] = []
    on_click(make(log))
    rt.feed_event(click(4, 5))
    wait(0)
    assert log == [expected]


def test_bound_methods_and_builtins_work_as_handlers(rt: Runtime) -> None:
    class Counter:
        def __init__(self) -> None:
            self.count = 0

        def hit(self, x: int) -> None:
            self.count += x

    counter = Counter()
    on_click(counter.hit)
    rt.feed_event(click(3, 0))
    wait(0)
    assert counter.count == 3
    on_key(print)  # signature unavailable on some versions: all values are passed
    on_key(None)


def test_registration_errors() -> None:
    with pytest.raises(TypeError, match="^on_click needs a function, but got 5"):
        on_click(5)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="^on_key needs a function"):
        on_key("a")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="on_click needs a function"):
        Circle().on_click(3)  # type: ignore[arg-type]

    def too_many(a, b, c):
        pass

    def too_many_key(a, b):
        pass

    def keyword_only(*, a):
        pass

    with pytest.raises(TypeError, match=r"on_click can only give its function 2 values \(x, y\)"):
        on_click(too_many)
    with pytest.raises(TypeError, match=r"on_key can only give its function 1 value \(key\)"):
        on_key(too_many_key)
    with pytest.raises(TypeError, match="Remove the extra parameters"):
        Circle().on_click(too_many)
    with pytest.raises(TypeError):
        on_click(keyword_only)


def test_each_registration_replaces_and_none_clears(rt: Runtime) -> None:
    log: list[str] = []
    ball = Circle()
    on_click(lambda: log.append("one"))
    on_click(lambda: log.append("two"))
    ball.on_click(lambda: log.append("ball"))
    rt.feed_event(click(target=1))
    rt.feed_event(click())
    wait(0)
    assert log == ["ball", "two"]
    ball.on_click(None)
    on_click(None)
    rt.feed_event(click(target=1))
    wait(0)
    assert log == ["ball", "two"]


def test_removed_shape_handler_is_not_called_canvas_handler_is(rt: Runtime) -> None:
    log: list[str] = []
    ball = Circle()
    ball.on_click(lambda: log.append("ball"))
    on_click(lambda: log.append("canvas"))
    ball.remove()
    rt.feed_event(click(target=1))
    wait(0)
    assert log == ["canvas"]


def test_events_dispatch_in_arrival_order_inside_wait_only(rt: Runtime) -> None:
    log: list[str] = []
    on_click(lambda x: log.append(f"click{x}"))
    on_key(lambda k: log.append(k))
    rt.feed_event(click(1))
    rt.feed_event(key("a"))
    rt.feed_event(click(2))
    assert log == []
    wait(0)
    assert log == ["click1", "a", "click2"]


def test_event_arriving_during_wait_is_handled_then_wait_continues(rt: Runtime) -> None:
    log: list[float] = []
    started = time.monotonic()
    on_key(lambda k: log.append(time.monotonic() - started))
    threading.Timer(0.05, rt.feed_event, args=[key("a")]).start()
    wait(0.2)
    assert len(log) == 1 and 0.04 <= log[0] < 0.15
    assert time.monotonic() - started >= 0.19


def test_handler_changes_are_flushed_during_dispatch(rt: Runtime, sent: Recorder) -> None:
    ball = Circle()
    on_key(lambda k: setattr(ball, "x", 50))
    rt.feed_event(key("a"))
    wait(0)
    assert sent.ops()[-1] == {"op": "update", "id": 1, "props": {"x": 50}}


def test_a_loop_of_wait_calls_does_not_flood_the_browser(
    rt: Runtime, sent: Recorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(runtime_module, "MIN_WAIT_FLUSH_INTERVAL", 0.05)
    ball = Circle()
    started = time.monotonic()
    steps = 0
    while time.monotonic() - started < 0.3:
        ball.x += 1
        wait()
        steps += 1
    assert steps > 1000
    assert len(sent.of("frame")) <= 8
    rt.flush()
    updates = [op for op in sent.ops() if op["op"] == "update"]
    assert updates[-1]["props"]["x"] == steps


def test_handler_errors_propagate_out_of_wait(rt: Runtime) -> None:
    def boom() -> None:
        raise ZeroDivisionError("kaboom")

    on_click(boom)
    rt.feed_event(click())
    with pytest.raises(ZeroDivisionError, match="kaboom"):
        wait(0)


def test_event_queue_is_bounded_and_drops_newest(rt: Runtime) -> None:
    seen: list[str] = []
    on_key(seen.append)
    for i in range(1005):
        rt.feed_event(key(str(i)))
    wait(0)
    assert len(seen) == 1000
    assert seen[0] == "0" and seen[-1] == "999"


def test_get_returns_live_objects_through_runtime_registry(rt: Runtime) -> None:
    ball = Circle(name="ball")
    assert get("ball") is ball
    assert rt.lookup("ball") is ball


def test_start_resets_the_scene_ids_names_and_handlers(sent: Recorder) -> None:
    runtime = Runtime(sent)
    runtime.start()
    try:
        assert current() is runtime
        Circle(name="ball")
        on_click(lambda: None)
        runtime.start()  # a new run
        assert runtime.scene.peek() == []
        assert current() is runtime
        Circle(name="ball")  # name is free again
        assert runtime.scene.peek()[0]["id"] == 1
        assert runtime._click is None
    finally:
        runtime.stop()
    assert current() is runtime_module._null


def test_flusher_thread_emits_on_its_own(sent: Recorder) -> None:
    runtime = Runtime(sent)
    runtime.start()
    try:
        Circle()
        wait_until(lambda: sent.of("frame"))
        runtime.print_stream("stdout").write("x")
        wait_until(lambda: sent.of("print"))
        canvas("gold")
        wait_until(lambda: sent.of("canvas"))
        assert threading.active_count() >= 2
    finally:
        runtime.stop()
    assert not any(t.name == "core-flusher" and t.is_alive() for t in threading.enumerate())


def test_stop_does_a_final_flush(sent: Recorder) -> None:
    runtime = Runtime(sent)
    runtime.start()
    Circle()
    runtime.print_stream("stderr").write("bye")
    runtime.stop()
    assert sent.of("frame") and sent.of("print")[-1]["text"] == "bye"
    assert current() is runtime_module._null


def test_flush_is_thread_safe_and_never_loses_or_duplicates_ops(sent: Recorder) -> None:
    runtime = Runtime(sent)
    runtime.start()
    try:
        flushers = [
            threading.Thread(target=lambda: [runtime.flush() for _ in range(200)]) for _ in range(3)
        ]
        for thread in flushers:
            thread.start()
        for _ in range(300):
            Circle()
        for thread in flushers:
            thread.join()
    finally:
        runtime.stop()
    ids = [op["id"] for op in sent.ops() if op["op"] == "create"]
    assert ids == list(range(1, 301))


def test_flusher_survives_a_failing_send_by_stopping_quietly() -> None:
    def broken(message: dict[str, Any]) -> None:
        raise BrokenPipeError

    runtime = Runtime(broken)
    runtime.start()
    try:
        Circle()
        wait_until(lambda: runtime._thread is not None and not runtime._thread.is_alive())
    finally:
        runtime._thread = None
        runtime._send = None
        runtime.stop()
