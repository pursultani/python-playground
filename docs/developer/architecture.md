# Architecture

A student edits `main.py`, runs `./run.sh main.py`, and a browser tab shows the result live.

```
 editor ── saves ──► main.py
                       │ (mtime poll, 0.25 s)
 ┌──────────────────── supervisor process (python -m core) ───────────────────────┐
 │  HTTP server (127.0.0.1)        file watcher        child process manager      │
 │   GET /            page                                                         │
 │   GET /events      SSE ──────────► browser                                      │
 │   POST /event      ◄──────────── clicks, keys                                   │
 │   POST /restart                                                                │
 │  Scene mirror: current objects, console lines, status, error  (for reconnects) │
 └───────────────▲───────────────────────────────────────┬────────────────────────┘
        JSON lines on child's stdout              JSON lines on child's stdin
                 │ frames, prints, error, end             │ click, key events
 ┌───────────────┴───────────────────────────────────────▼────────────────────────┐
 │ child process (core.runner): compiles + execs the student's file                 │
 │   namespace pre-loaded with the whole API (no imports)                           │
 │   Runtime: scene (pending ops), flusher thread (60 fps), event queue, wait()     │
 └──────────────────────────────────────────────────────────────────────────────────┘
```

## Key decisions

| Decision | Why |
|---|---|
| Python runs in a **child process**, killed and restarted on every save | A student's `while True:` can never hang the page or the tool. |
| Browser is a **pure renderer**; state lives in Python | Python is the lesson; the page has no program logic. |
| **SVG** rendering with CSS transitions | One DOM node per object, attribute mapping is trivial, smooth motion for free, crisp at any size. |
| **Stdlib only**: `http.server` + Server-Sent Events, mtime polling | Students install nothing. Python 3.10+. |
| **No imports** in student code: runner pre-loads the API into the script's globals | Imports are not a day-one concept. `import random`/`math` still work. |
| Fixed **800x600** logical canvas, origin at the centre, **+y up** | Matches maths class; scales to any window. |
| **No hidden event loop**: handlers run only inside `wait()` | The event loop is a teaching concept; the student writes `while True: wait(...)`. |
| Updates **coalesced** and flushed at 60 fps | Tight loops cannot flood the browser. |
| Ids by **creation order**; browser reuses nodes across re-runs | No flicker while typing; transitions animate old state to new. |
| Program **lifecycle is visible**: starting, running, finished, crashed | "A program starts and ends" is a core concept. |
| **Property typos raise errors** (`ball.colour`) | The most common beginner mistake becomes a teachable message. |
| Editor support through a generated **`__builtins__.pyi`** | Pyright/Pylance treat the API as builtins: autocomplete, hover docs, real typo detection, no import needed. Verified with Pyright. |

## Module map (`engine/lib/core`)

| Module | Role |
|---|---|
| `__init__` | Public API surface, `__all__`, `namespace()` |
| `_props` | `prop()` descriptor factory and validators |
| `_colors` | CSS colour validation and "did you mean" |
| `_scene` | Object ids, pending op coalescing |
| `_runtime` | Child-side runtime: flusher thread, event queue, `wait`, print capture |
| `shapes`, `guides`, `api` | `Circle`..., `Grid`/`Axis`, `canvas`/`wait`/`get`/`on_click`/`on_key` |
| `runner` | Child entry point: exec the script, format errors, report lifecycle |
| `_errors` | Traceback trimming and error payloads |
| `_protocol` | Message constants, JSON-lines helpers, scene mirror |
| `supervisor` | HTTP/SSE server, watcher, child management, CLI plumbing |
| `__main__` | CLI (`python -m core script.py`) |
| `static/` | `index.html`, `app.js`, `style.css` |

See the specs in `docs/developer/specs/` for exact behavior.
