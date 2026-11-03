"""Pending scene operations: ids in creation order and op coalescing."""

from __future__ import annotations

from typing import Any


class Scene:
    """Collects the changes made since the last flush, one op per object id."""

    def __init__(self) -> None:
        self._ops: dict[int, dict[str, Any]] = {}
        self._next_id = 1

    def create(self, type_: str, props: dict[str, Any]) -> int:
        """Assign the next id and queue a `create` op."""
        id_ = self._next_id
        self._next_id += 1
        self._ops[id_] = {"op": "create", "id": id_, "type": type_, "props": dict(props)}
        return id_

    def update(self, id_: int, props: dict[str, Any]) -> None:
        """Queue changed properties, merging into a pending create or update."""
        pending = self._ops.get(id_)
        if pending is None:
            self._ops[id_] = {"op": "update", "id": id_, "props": dict(props)}
        elif pending["op"] != "remove":
            pending["props"].update(props)

    def remove(self, id_: int) -> None:
        """Queue a removal. Removing something the browser never saw cancels out."""
        pending = self._ops.get(id_)
        if pending is not None and pending["op"] == "create":
            del self._ops[id_]
        else:
            self._ops[id_] = {"op": "remove", "id": id_}

    def peek(self) -> list[dict[str, Any]]:
        """Return the pending ops without clearing them."""
        return list(self._ops.values())

    def drain(self) -> list[dict[str, Any]]:
        """Return the pending ops (first-touch order) and clear them."""
        ops = list(self._ops.values())
        self._ops.clear()
        return ops
