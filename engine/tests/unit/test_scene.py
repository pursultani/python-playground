from __future__ import annotations

from core._scene import Scene


def test_ids_start_at_one_in_creation_order() -> None:
    scene = Scene()
    assert [scene.create("circle", {}) for _ in range(3)] == [1, 2, 3]


def test_create_then_update_merges_into_create() -> None:
    scene = Scene()
    scene.create("circle", {"x": 0, "y": 0})
    scene.update(1, {"x": 5})
    assert scene.drain() == [{"op": "create", "id": 1, "type": "circle", "props": {"x": 5, "y": 0}}]


def test_update_then_update_merges() -> None:
    scene = Scene()
    scene.update(4, {"x": 1})
    scene.update(4, {"y": 2, "x": 3})
    assert scene.drain() == [{"op": "update", "id": 4, "props": {"x": 3, "y": 2}}]


def test_create_then_remove_cancels_out() -> None:
    scene = Scene()
    scene.create("circle", {})
    scene.update(1, {"x": 1})
    scene.remove(1)
    assert scene.drain() == []


def test_update_then_remove_becomes_remove() -> None:
    scene = Scene()
    scene.update(1, {"x": 1})
    scene.remove(1)
    assert scene.drain() == [{"op": "remove", "id": 1}]


def test_remove_alone_and_updates_after_remove_are_ignored() -> None:
    scene = Scene()
    scene.remove(2)
    scene.update(2, {"x": 1})
    assert scene.drain() == [{"op": "remove", "id": 2}]


def test_first_touch_order_is_kept() -> None:
    scene = Scene()
    scene.create("circle", {})
    scene.create("circle", {})
    scene.update(9, {"x": 1})
    scene.update(1, {"x": 1})
    scene.update(2, {"x": 1})
    scene.remove(9)
    assert [op["id"] for op in scene.drain()] == [1, 2, 9]


def test_drain_clears_and_ids_keep_counting() -> None:
    scene = Scene()
    scene.create("circle", {})
    assert len(scene.drain()) == 1
    assert scene.drain() == []
    assert scene.create("circle", {}) == 2
    scene.update(1, {"x": 1})
    assert [op["op"] for op in scene.peek()] == ["create", "update"]
    assert len(scene.peek()) == 2


def test_create_copies_its_props() -> None:
    scene = Scene()
    props = {"x": 0}
    scene.create("circle", props)
    props["x"] = 99
    assert scene.peek()[0]["props"] == {"x": 0}
