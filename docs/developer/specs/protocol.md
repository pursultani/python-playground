# Spec: processes, lifecycle and wire protocol

Owners: WP-B (supervisor, runner, errors, protocol module), WP-A (runtime on the child side).
Shared contract: the **runtime seam** below.

## CLI

```
python -m core <script.py> [--port N] [--no-browser]
```

- Binds to **127.0.0.1** only. Default port **8765**; if busy, try the next ports up to +20; then
  fail with a friendly message. `--port N` uses exactly N (fail if busy).
- Opens the page with `webbrowser.open` unless `--no-browser`.
- Missing/unreadable script: friendly message and exit code 2. Python < 3.10: friendly message.
- Terminal output (stdout), plain and short:
  `Python Playground running at http://127.0.0.1:8765  (Ctrl+C to stop)`,
  `Watching main.py`, `main.py changed - restarting`, `Program finished`,
  `Program stopped by an error: NameError: name 'x' is not defined (main.py, line 3)`.
  `print` output is **not** echoed to the terminal (the browser console is canonical).
- Ctrl+C or SIGTERM (also during startup): kill the child, close the server, exit 0, no
  traceback. The SIGTERM handler is installed before the server starts.
- `run.sh` is a thin wrapper (see `tooling.md`). It exports `PLAYGROUND_PROG` (the way it was
  called, e.g. `./run.sh`); terminal messages and `--help` use it instead of `python -m core`
  (default when unset: `python -m core`).
- **`sys.path`**: `run.sh` starts the supervisor with `python -c` boot code that removes `''`
  and the current directory from `sys.path` *before* importing `core`
  (`runpy.run_module("core", run_name="__main__")`), so a student's `queue.py`, `json.py` or
  `core.py` cannot replace the engine's modules. `PYTHONPATH` is kept.
- **Name clashes**: at the start of every run, each `*.py` directly in the script folder whose
  name is a standard-library module (`sys.stdlib_module_names`, except `test`, `this`,
  `antigravity`, `idlelib`, dunder names) or `core` produces a plain-English warning, e.g.
  `random.py has the same name as a Python module that comes with Python, so Python's own random
  can't be used. Rename it, for example my_random.py.` It is shown as a `stderr` console chunk
  (`Warning: ...`, first in the run's console) and once on the terminal (again only if it
  changes). If the script itself has such a name it still runs, with different wording.

## Lifecycle

States: `starting` -> `running` -> `finished` | `crashed`. A save or Restart kills the child
(state is replaced by a fresh `starting` for a new `run` number).

- `starting`: child process spawned, script not yet executing.
- `running`: the runner sent `hello` (script is executing).
- `finished`: script ran to its last line or called `exit()`/`sys.exit()` (`SystemExit`).
  The child then exits. Pending events are dropped. The last drawing stays in the browser.
- `crashed`: uncaught exception (including `SyntaxError`, errors in handlers) **or** the child
  died without sending `end`/`error` (message: `The program stopped unexpectedly`).
- The supervisor and browser stay alive in every state. Restart: file change in the script's
  directory (any `*.py` directly inside it, or one level of sub-directories) or `POST /restart`.
- Watcher: poll mtimes (and file sizes) every 0.25 s; restart when anything changed, debounced
  so one save causes one restart. Work is capped: `*.py` files directly in the script folder, plus
  one level of sub-folders, skipping hidden, `__*__`, `venv`, `env`, `node_modules`,
  `site-packages` folders, sub-folders with more than 200 entries, and anything past 50
  sub-folders or 500 files. If the script folder is the home folder or `/`, sub-folders are not
  scanned at all.
- Killing the child: the child is its own session/process group (`start_new_session=True`), so on
  POSIX the supervisor sends `SIGTERM` to the whole group (programs the script started with
  `subprocess` die too), waits up to 1 s, then `SIGKILL`s the group. Leftover group members are
  also killed whenever a child ends by itself. On Windows: `terminate()` then `kill()` on the
  child only. If the supervisor dies, the child sees stdin EOF and kills its own group.

## Child process

Started by the supervisor as `[sys.executable, "-u", "-c", CHILD_BOOT, "<abs script path>"]`
with pipes for stdin/stdout, `PYTHONDONTWRITEBYTECODE=1` and cwd = script directory.
`CHILD_BOOT` removes `''` and the current directory (= the script directory) from `sys.path`,
then runs `core.runner.run()`. The runner pre-imports the modules the engine needs, and only then
appends the script directory to the **end** of `sys.path` (so students can split code into
modules, but standard-library names always win over their files).

The runner (`core.runner`):

1. Keeps a private handle on the **protocol channel** = a dup of fd 1, then points fd 1 at fd 2
   so stray C-level writes cannot corrupt the protocol. Writes are one JSON object per line,
   `ensure_ascii=False`, flushed, guarded by a lock.
2. Creates the `Runtime` (below), starts it, redirects `sys.stdout`/`sys.stderr` to the runtime's
   print streams, sets `sys.stdin` to a stream whose `read`/`readline`/iteration raise
   `EOFError("input() does not work in Python Playground. Use on_click or on_key to get answers
   from the player.")`.
3. Starts a daemon thread reading **stdin** lines (events) and calling `runtime.feed_event(event)`.
   On stdin EOF (supervisor died) the child exits immediately with `os._exit(0)`.
4. Sends `{"t":"hello"}`.
5. Reads the script (`tokenize.open`), `compile(source, abs_path, "exec")`, executes it in
   `{"__name__": "__main__", "__file__": abs_path, **core.namespace()}`.
6. On normal completion or `SystemExit`: `runtime.stop()` (final flush), send `{"t":"end"}`, exit 0.
   A file that cannot be used gives an `error` payload with `kind: "Error"`, `frames: []` and a
   friendly message naming only the file name: `main.py isn't saved as UTF-8. Save the file
   again as UTF-8.`, `main.py has a null byte in it ...`, `I can't read main.py. ...`,
   `I can't find main.py. ...`.
7. On any other exception (incl. `SyntaxError` at compile time): final flush, send
   `{"t":"error", ...}` (payload below), exit 1. `KeyboardInterrupt` in the child: treat as
   finished.

### The runtime seam (contract between WP-A and WP-B)

WP-A provides `core/_runtime.py`:

```python
class Runtime:
    def __init__(self, send: Callable[[dict], None]) -> None: ...   # send = write one message
    def start(self) -> None          # becomes the active runtime (module global), starts flusher thread
    def stop(self) -> None           # final flush, stop flusher thread, deactivate
    def flush(self) -> None          # send pending frame/print/canvas messages now (thread-safe)
    def feed_event(self, event: dict) -> None   # thread-safe, non-blocking, bounded queue (1000, drop newest)
    def print_stream(self, name: str) -> TextIO # "stdout" | "stderr": file-like, line-buffering not required
def current() -> Runtime            # the active runtime; if none, a null runtime that records ops in
                                    # memory without sending (so importing/using `core` in tests works)
```

The flusher thread calls `flush()` every 1/60 s. `flush()` emits (only when non-empty):
`{"t":"frame","ops":[...]}`, `{"t":"canvas","background":...}`, `{"t":"print","text":..., "stream":...}`.
Print chunks are coalesced per stream, keeping order within a stream.

`core/__init__.py` exposes `namespace()`. WP-B must not import anything else from WP-A's
modules except `core.namespace`, `core._runtime.Runtime`.

## Messages

All JSON objects with a `"t"` type.

### Child -> supervisor (stdout JSON lines)

| `t` | Fields | Meaning |
|---|---|---|
| `hello` | | Script is about to execute. |
| `frame` | `ops`: list of op | Scene changes (coalesced). |
| `canvas` | `background`: str | Background colour changed. |
| `print` | `text`: str, `stream`: `"stdout"`\|`"stderr"` | Console output chunk (raw, may lack newline). |
| `end` | | Normal completion. |
| `error` | see "Error payload" | Uncaught exception. |

Ops (inside `frame.ops`), ordered; at most one per object id per frame:

```json
{"op":"create","id":1,"type":"circle","props":{"x":0,"y":0,"radius":50,"color":"steelblue","rotation":0,"title":"","opacity":1,"visible":true}}
{"op":"update","id":1,"props":{"x":10}}
{"op":"remove","id":1}
```

- `type` in: `circle`, `rectangle`, `triangle`, `line`, `text`, `grid`, `axis`.
- `props` carry **all** synced properties on create (with defaults filled in), only the changed
  ones on update. `name` is never sent.
- Ids are small integers assigned in creation order starting at 1 for each run.
- Coalescing: `create`+`update` -> `create` with merged props; `update`+`update` -> merged;
  `create`+`remove` in the same frame -> nothing; `update`+`remove` -> `remove`.
  First-touch order of ids is preserved (so DOM stacking = creation order).

### Supervisor -> browser (Server-Sent Events on `GET /events`)

The stream starts with `retry: 500` (fast reconnects). Each SSE message is `data: <json>\n\n`.
A `: keep-alive` comment every 15 s.

| `t` | Fields | Meaning |
|---|---|---|
| `snapshot` | `run`, `state`, `script` (file name), `background`, `objects`: list of `{id,type,props}` (full current props, creation order), `console`: list of `{text,stream}` (last 2000 chunks, coalesced), `error`: error payload or null | Sent first on every (re)connect. Browser replaces everything with no transitions. |
| `run` | `run`: int | A new run begins (state `starting`). Browser clears console and error, background -> white, marks all nodes stale (see `browser.md`). |
| `status` | `run`, `state` | `starting`/`running`/`finished`/`crashed`. |
| `frame`, `canvas`, `print`, `error` | as from the child | Forwarded as they arrive (`print` stream kept). |

The supervisor keeps a **scene mirror** (apply every op, background, console buffer capped at
2000 chunks, current status, last error) to build `snapshot`. It is reset on each `run`.
Message order for one run: `run`, `status(starting)`, [`status(running)`], frames/prints...,
(`status(finished)` | `error` then `status(crashed)`).

### Browser -> supervisor (HTTP)

| Request | Body | Effect |
|---|---|---|
| `GET /` | | `static/index.html` |
| `GET /static/<file>` | | Static files from `core/static` (no directory traversal; correct MIME types; `Cache-Control: no-store`). |
| `GET /events` | | SSE stream. |
| `POST /event` | `{"t":"click","x":int,"y":int,"target":int\|null}` or `{"t":"key","key":str}` | Forward to child stdin as one JSON line. Respond `204`. Dropped (still `204`) if no child is running. Malformed JSON: `400`. |
| `POST /restart` | | Kill and restart the child. `204`. |

`ThreadingHTTPServer` with `daemon_threads = True`; SSE handlers must exit cleanly when the
client disconnects or the server shuts down. No CORS headers (same origin only).

Security checks (basic DNS-rebinding and cross-site protection), all answered with `403`:
the `Host` header must be `127.0.0.1`, `localhost` or `[::1]` **with the server's own port**
(parsed strictly: the last `:` separates the port; `@`, `/`, spaces, bad ports are refused); on
`POST`, an `Origin` header must be `http://` plus such a host and the same port (`null` is
refused). HTML responses carry `X-Frame-Options: DENY` and
`Content-Security-Policy: frame-ancestors 'none'`.

### Supervisor -> child (stdin JSON lines)

```json
{"t":"click","x":12,"y":-40,"target":3}
{"t":"key","key":"ArrowLeft"}
```

The `target` is the creation-order id of the topmost shape under the cursor or `null`. The
runtime maps ids to objects.

## Error payload

```json
{
  "t": "error",
  "kind": "NameError",
  "message": "name 'bal' is not defined. Did you mean: 'ball'?",
  "frames": [
    {"file": "main.py", "line": 12, "function": "<module>", "code": "go()", "col": 1, "end_col": 3},
    {"file": "main.py", "line": 8, "function": "go", "code": "bal.x += 1", "col": 5, "end_col": 8}
  ],
  "context": [{"line": 6, "code": "def go():"}, {"line": 7, "code": "    ..."}, {"line": 8, "code": "    bal.x += 1"}]
}
```

- `frames`: only frames from **the student's files** (script, and other `.py` files inside the
  script directory), outermost first. Framework frames and stdlib are dropped. The **last** frame
  is the one highlighted. Handler errors naturally show `wait(...)`'s caller frame then the
  handler frame. If no user frames exist (should not happen), `frames` is `[]`.
- `file` is relative to the script directory (`main.py`). `function` is `<module>` for top level.
- `col`/`end_col`: **1-based character columns**, end exclusive; omit when unknown (Python 3.10
  gives no column info for runtime errors). Convert from Python's UTF-8 byte offsets
  (`FrameSummary.colno`/`end_colno`) to character columns. Multi-line spans: highlight to the end
  of the first line.
- `message`: for most exceptions, `str(exc)` plus any suggestion Python 3.12+ adds
  (use `traceback.format_exception_only`, strip the `Kind: ` prefix and trailing newline).
  On Python 3.10/3.11, a `NameError` (candidates: the failing frame's locals, globals and
  builtins) or `AttributeError` (candidates: `dir(exc.obj)`, private names only when the typo is
  private) without a suggestion gets `. Did you mean: 'ball'?` from `difflib.get_close_matches`.
  For `SyntaxError`/`IndentationError`: `exc.msg` (never the multi-line formatted text),
  with `frames` = one frame from `lineno`/`offset`/`end_offset`/`text`.
  Our own friendly errors already read well and pass through unchanged.
- `context`: up to 2 source lines before and 1 after the highlighted line, read from the file
  at error time (tabs expanded to 4 spaces consistently in `code` and columns).
- Exception chains (`__cause__`/`__context__`) are ignored: only the final exception is shown.
- Errors raised while formatting must never crash the runner: fall back to
  `{"kind": ..., "message": ..., "frames": [], "context": []}`.

## Flood protection (added during integration)

- `wait()` flushes immediately but at most every 1/120 s; the 60 Hz flusher sends whatever a
  skipped flush left behind. A tight `while True: obj.x += 1; wait()` therefore cannot overload
  the supervisor.
- At most 64 KB of printed text is sent per flush; the rest is dropped and a notice
  ("Too much was printed too fast ... Try adding wait(0.1)") goes to `stderr`.
- The supervisor's console mirror and the page's console are each capped at 200,000 characters
  (in addition to the 2000-chunk cap).

## Threads and safety summary

Child: main thread (script, `wait`, handlers) + stdin reader + flusher. Shared state (pending
ops, print buffers, event queue) is lock-protected or `queue.Queue`. Supervisor: HTTP threads,
watcher thread, child-stdout reader thread. All writes to the child's stdin and all SSE
broadcasts go through one lock or per-client queues.
