import io
import json
import threading

from core import _protocol as proto


def create(object_id, type_="circle", **props):
    return {"op": "create", "id": object_id, "type": type_, "props": props}


def frame(*ops):
    return {"t": "frame", "ops": list(ops)}


class TestSceneMirror:
    def test_new_mirror_snapshot(self):
        snap = proto.SceneMirror("main.py").snapshot()
        assert snap == {
            "t": "snapshot",
            "run": 0,
            "state": "starting",
            "script": "main.py",
            "background": "white",
            "objects": [],
            "console": [],
            "error": None,
        }

    def test_create_update_remove(self):
        mirror = proto.SceneMirror("main.py")
        mirror.apply(frame(create(1, x=0, color="red"), create(2, "rectangle", x=5)))
        mirror.apply(frame({"op": "update", "id": 1, "props": {"x": 10}}))
        mirror.apply(frame({"op": "remove", "id": 2}))
        objects = mirror.snapshot()["objects"]
        assert objects == [{"id": 1, "type": "circle", "props": {"x": 10, "color": "red"}}]

    def test_objects_keep_creation_order(self):
        mirror = proto.SceneMirror()
        mirror.apply(frame(create(1), create(2), create(3)))
        mirror.apply(frame({"op": "update", "id": 1, "props": {"x": 1}}))
        mirror.apply(frame({"op": "remove", "id": 2}, create(4)))
        assert [o["id"] for o in mirror.snapshot()["objects"]] == [1, 3, 4]

    def test_update_or_remove_of_unknown_id_is_ignored(self):
        mirror = proto.SceneMirror()
        mirror.apply(frame({"op": "update", "id": 9, "props": {"x": 1}}, {"op": "remove", "id": 9}))
        assert mirror.snapshot()["objects"] == []

    def test_malformed_ops_are_ignored(self):
        mirror = proto.SceneMirror()
        mirror.apply({"t": "frame", "ops": ["nope", 3, {"op": "create"}, {"op": "update"}]})
        mirror.apply({"t": "frame", "ops": "nope"})
        mirror.apply({"t": "canvas", "background": 5})
        mirror.apply({"t": "print", "text": 5})
        assert mirror.snapshot()["objects"] == []
        assert mirror.snapshot()["background"] == "white"
        assert mirror.snapshot()["console"] == []

    def test_snapshot_is_a_copy(self):
        mirror = proto.SceneMirror()
        mirror.apply(frame(create(1, x=0)))
        snap = mirror.snapshot()
        snap["objects"][0]["props"]["x"] = 99
        assert mirror.snapshot()["objects"][0]["props"]["x"] == 0

    def test_canvas_sets_background(self):
        mirror = proto.SceneMirror()
        mirror.apply({"t": "canvas", "background": "black"})
        assert mirror.snapshot()["background"] == "black"

    def test_adjacent_prints_on_one_stream_are_merged(self):
        mirror = proto.SceneMirror()
        for text in ("a", "b\n", "c"):
            mirror.apply({"t": "print", "text": text, "stream": "stdout"})
        assert mirror.snapshot()["console"] == [{"text": "ab\nc", "stream": "stdout"}]

    def test_streams_are_not_merged_with_each_other(self):
        mirror = proto.SceneMirror()
        mirror.apply({"t": "print", "text": "out", "stream": "stdout"})
        mirror.apply({"t": "print", "text": "err", "stream": "stderr"})
        mirror.apply({"t": "print", "text": "more", "stream": "stderr"})
        mirror.apply({"t": "print", "text": "out2", "stream": "stdout"})
        assert mirror.snapshot()["console"] == [
            {"text": "out", "stream": "stdout"},
            {"text": "errmore", "stream": "stderr"},
            {"text": "out2", "stream": "stdout"},
        ]

    def test_empty_print_is_ignored(self):
        mirror = proto.SceneMirror()
        mirror.apply({"t": "print", "text": "", "stream": "stdout"})
        assert mirror.snapshot()["console"] == []

    def test_console_is_capped_at_2000_chunks(self):
        mirror = proto.SceneMirror()
        for index in range(2500):
            stream = "stdout" if index % 2 == 0 else "stderr"
            mirror.apply({"t": "print", "text": str(index), "stream": stream})
        console = mirror.snapshot()["console"]
        assert len(console) == proto.MAX_CONSOLE_CHUNKS
        assert console[0]["text"] == "500"
        assert console[-1]["text"] == "2499"

    def test_endless_output_on_one_stream_stays_bounded(self):
        mirror = proto.SceneMirror()
        chunk = "x" * 1000
        for _ in range(100):
            mirror.apply({"t": "print", "text": chunk, "stream": "stdout"})
        console = mirror.snapshot()["console"]
        assert sum(len(c["text"]) for c in console) == 100_000
        assert all(len(c["text"]) <= proto.MAX_CHUNK_CHARS + 1000 for c in console)
        assert len(console) > 1

    def test_error_is_stored(self):
        mirror = proto.SceneMirror()
        payload = {"t": "error", "kind": "NameError", "message": "m", "frames": [], "context": []}
        mirror.apply(payload)
        assert mirror.snapshot()["error"] == payload

    def test_reset_starts_a_blank_run(self):
        mirror = proto.SceneMirror("main.py")
        mirror.apply(frame(create(1)))
        mirror.apply({"t": "canvas", "background": "red"})
        mirror.apply({"t": "print", "text": "x", "stream": "stdout"})
        mirror.apply({"t": "error", "kind": "E", "message": "", "frames": [], "context": []})
        mirror.state = "crashed"
        mirror.reset(7)
        snap = mirror.snapshot()
        assert (snap["run"], snap["state"], snap["script"]) == (7, "starting", "main.py")
        assert snap["objects"] == [] and snap["console"] == []
        assert snap["background"] == "white" and snap["error"] is None


class TestValidateEvent:
    def test_click(self):
        event = {"t": "click", "x": 12, "y": -40, "target": 3}
        assert proto.validate_event(event) == event

    def test_click_without_target_and_float_coordinates(self):
        event = proto.validate_event({"t": "click", "x": 1.4, "y": 2.6, "target": None})
        assert event == {"t": "click", "x": 1, "y": 3, "target": None}
        assert proto.validate_event({"t": "click", "x": 1, "y": 2}) == {
            "t": "click",
            "x": 1,
            "y": 2,
            "target": None,
        }

    def test_extra_fields_are_dropped(self):
        event = proto.validate_event({"t": "key", "key": "a", "evil": 1})
        assert event == {"t": "key", "key": "a"}

    def test_key(self):
        assert proto.validate_event({"t": "key", "key": "ArrowLeft"}) == {
            "t": "key",
            "key": "ArrowLeft",
        }

    def test_invalid_events(self):
        bad = [
            None,
            [],
            "click",
            {},
            {"t": "wiggle"},
            {"t": "click"},
            {"t": "click", "x": "1", "y": 2, "target": None},
            {"t": "click", "x": True, "y": 2, "target": None},
            {"t": "click", "x": float("nan"), "y": 2, "target": None},
            {"t": "click", "x": 1, "y": 2, "target": "3"},
            {"t": "click", "x": 1, "y": 2, "target": True},
            {"t": "key"},
            {"t": "key", "key": ""},
            {"t": "key", "key": 5},
            {"t": "key", "key": "x" * 100},
        ]
        for item in bad:
            assert proto.validate_event(item) is None, item


class TestJsonLines:
    def test_writer_text_stream(self):
        stream = io.StringIO()
        proto.JsonLineWriter(stream).write({"t": "print", "text": "héllo\n", "stream": "stdout"})
        assert stream.getvalue() == '{"t":"print","text":"héllo\\n","stream":"stdout"}\n'

    def test_writer_binary_stream_is_utf8(self):
        stream = io.BytesIO()
        proto.JsonLineWriter(stream).write({"t": "x", "v": "é"})
        assert stream.getvalue() == '{"t":"x","v":"é"}\n'.encode()

    def test_writer_is_thread_safe(self):
        stream = io.StringIO()
        writer = proto.JsonLineWriter(stream)

        def work(worker):
            for index in range(200):
                writer.write({"t": "print", "text": f"{worker}-{index}" * 20})

        threads = [threading.Thread(target=work, args=(n,)) for n in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        lines = stream.getvalue().splitlines()
        assert len(lines) == 8 * 200
        assert all(json.loads(line)["t"] == "print" for line in lines)

    def test_reader_skips_garbage(self):
        data = b'{"t":"hello"}\nnot json\n\n[1,2]\n{"t":"end"}\n'
        assert list(proto.read_messages(io.BytesIO(data))) == [{"t": "hello"}, {"t": "end"}]

    def test_reader_replaces_bad_utf8(self):
        data = b'{"t":"print","text":"a\xffb"}\n'
        (message,) = proto.read_messages(io.BytesIO(data))
        assert message["text"] == "a\ufffdb"

    def test_reader_text_stream(self):
        assert list(proto.read_messages(io.StringIO('{"t":"end"}\n'))) == [{"t": "end"}]

    def test_sse_event_format(self):
        assert proto.sse_event({"t": "run", "run": 1}) == b'data: {"t":"run","run":1}\n\n'

    def test_dumps_never_contains_a_raw_newline(self):
        assert "\n" not in proto.dumps({"text": "a\nb\r\nc\u2028d"})
