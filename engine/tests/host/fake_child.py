"""A stand-in for ``core.runner`` used by the supervisor tests.

Runs the "script" as plain Python with three helpers in its globals:

* ``send(message)``: write one protocol message to the supervisor.
* ``read_event()``: block until the supervisor forwards an event (``None`` on EOF).
* ``say(text, stream="stdout")``: shortcut for a ``print`` message.

Like the real runner it sends ``hello`` first, then ``end`` or ``error`` when the script is over.
"""

import json
import sys

from core._errors import build_error_payload


def send(message):
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def read_event():
    line = sys.stdin.readline()
    return json.loads(line) if line else None


def say(text, stream="stdout"):
    send({"t": "print", "text": text, "stream": stream})


def main(path):
    import os

    send({"t": "hello"})
    namespace = {
        "__name__": "__main__",
        "__file__": path,
        "send": send,
        "read_event": read_event,
        "say": say,
    }
    sys.path.insert(0, os.path.dirname(path))
    try:
        with open(path, "rb") as handle:
            exec(compile(handle.read(), path, "exec"), namespace)
    except SystemExit:
        send({"t": "end"})
        return 0
    except BaseException as exc:
        send(build_error_payload(exc, os.path.dirname(path)))
        return 1
    send({"t": "end"})
    return 0


if __name__ == "__main__":
    code = main(sys.argv[1])
    sys.stdout.flush()
    sys.exit(code)
