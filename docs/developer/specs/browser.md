# Spec: the browser page

Owner: WP-C. Files: `engine/lib/core/static/{index.html,app.js,style.css}`. Vanilla JS, no
dependencies, no network access, no build step. Works in current Chrome, Firefox, Safari.
Look and feel matters: the page should feel friendly and polished, like a toy that makes
programming tangible. Test visually with screenshots.

## Layout

```
┌────────────────────────────────────────────────────────────┐
│ ▶ Python Playground      main.py     ● Running…   [Restart]│  top bar
├────────────────────────────────────────────────────────────┤
│  [error panel, overlays the top of the canvas area]        │
│            ┌──────────────────────────┐                    │
│            │      800 x 600 canvas    │  scaled to fit,    │
│            │                          │  4:3, centred      │
│            └──────────────────────────┘                    │
├────────────────────────────────────────────────────────────┤
│ ▾ Console (3)                                    [Clear]   │  toggle panel
│   Hello!                                                   │
└────────────────────────────────────────────────────────────┘
```

- Full-viewport flex column. The canvas area takes the remaining height; the SVG keeps 4:3
  (`viewBox="-400 -300 800 600"`, `preserveAspectRatio="xMidYMid meet"`), has rounded corners
  (12px), a soft shadow and a faint border, on a muted page background.
- **Console panel** below the canvas: header with a toggle (chevron + "Console" + number of
  lines) and a Clear button. **Open by default**, state persisted in `localStorage`. Monospace,
  `stdout` normal, `stderr` red-tinted, auto-scroll to bottom unless the user scrolled up,
  capped at 2000 chunks (drop oldest). `white-space: pre-wrap`. Cleared on each new run.
  Resizable height is not needed; fixed max height ~30vh with its own scroll.
- Palette via CSS variables; system font stack; good contrast; supports
  `prefers-color-scheme: dark` for the page chrome only (the canvas background is whatever the
  program sets, default white).
- `<title>`: `Python Playground`; shows the script name in the top bar from `snapshot.script`.

## Status badge (program lifecycle)

| State | Badge text | Style |
|---|---|---|
| `starting` | `Starting…` | grey |
| `running` | `Running…` | green, gently pulsing dot |
| `finished` | `Program finished ✓` | blue |
| `crashed` | `Stopped by an error ✗` | red |
| connection lost | `Disconnected: waiting for the playground…` | orange banner under top bar |

Connection: one `EventSource('/events')`. On `error`/close show the disconnected state and
rely on automatic reconnection; the next `snapshot` restores everything. The **Restart** button
`POST /restart`s.

## Error panel

Shown when an `error` message arrives (or `snapshot.error` is set). Appears over the top of the
canvas area (absolutely positioned card, max-width ~720px, centred), the canvas is dimmed
(`opacity .45` + slight grayscale transition) while an error is visible. Content:

1. Title line: `⚠ {kind}` and the message, large and readable.
2. `File main.py, line 8` for the last frame; if more frames, a compact "called from" list above
   it (outermost first, `main.py, line 12 in <module>`), at most 4, then `…`.
3. **Code snippet** from `context`: monospace, line numbers, the error line highlighted with a
   tinted background and a left accent bar; if `col`/`end_col` exist, underline exactly that
   span (wavy red underline or background mark), computed on the character columns of `code`.
   Only code is highlighted; no stack-trace noise.
4. Cleared when a new `run` message arrives or the error is gone from a snapshot.

## Rendering model

State: `Map<id, Node>` where Node = `{type, el, props}`. All shapes live in `<g id="shapes">`,
guides (`grid`, `axis`) in `<g id="guides">` **behind** shapes; both inside the SVG. A background
`<rect>` covers the canvas and takes `background`. Guides have `pointer-events: none`.

Coordinates: logical `(x, y)` -> SVG `(x, -y)`. Each shape is a `<g data-id>` with
`style.transform = translate(Xpx, Ypx) rotate(-Rdeg)` (`transform-box: fill-box` not needed;
origin is 0,0 of the group). Children geometry is centred on 0,0:

| type | Elements |
|---|---|
| circle | `<circle r>` fill=color |
| rectangle | `<rect x=-w/2 y=-h/2 width height>` rx small (4) |
| triangle | `<polygon points="0,-h/2  w/2,h/2  -w/2,h/2">` (y flipped already: apex up on screen) |
| line | `<line x1=0 y1=0 x2=(x2-x) y2=-(y2-y)>` stroke=color, stroke-width=width, round caps; **no rotation**; group translates to start |
| text | `<text text-anchor=middle dominant-baseline=central font-size=size>` fill=color; font stack incl. emoji |
| grid | `<path>` lines at multiples of `size` across the canvas, stroke/width/dash by style (`dashed` -> `8 6`, `dotted` -> `1 5` with round caps), plus opacity |
| axis | two lines through the origin, ticks every `size` (length 8), and when `labels` numbers at ticks (skip 0 label or show a single `0`), font-size 12, offset from the axis; labels use logical values (y labels positive upward) |

Guide sizes are drawn exactly as asked (`Grid(size=1)` has a line every unit). The only clamp is a
safety limit: a step below 0.4 canvas units (more than 2000 lines/ticks per direction) is
drawn as 0.4. Axis **tick marks** are never thinned. Axis **labels** are thinned so they cannot
overlap: only every Nth tick gets a number (N chosen so labelled ticks are at least 34 px apart,
so `Axis(size=10)` labels 40, 80, ...); each shown label is the true value of its tick.

- `title` (not for text/guides): `<text>` at the shape's centre (midpoint for line) in the
  same group, `paint-order: stroke`, white 3px stroke halo, dark fill, pointer-events none,
  hidden when empty; font-size 16 unless trivially small.
- Shape common props: `opacity` -> `style.opacity`; `visible: false` -> `display: none`.
- **Transitions:** `transition: transform .12s ease-out, opacity .12s, fill .12s, stroke .12s`
  on shape groups/elements. **Disable transitions for a node's first paint** (create with the
  class `no-anim`, remove it on the next animation frame) and for snapshots.
- Update unknown/old props gracefully: ignore unknown props and unknown types (log to console).
- Colours are CSS strings passed through; the engine already validated them.

## Run boundaries and re-run smoothness

- On `run`: set `staleIds = new Set(all current ids)`, clear console and error, state `starting`. **Do not remove nodes yet, and keep the old background**: the new run's `canvas` background (no transition) replaces it, or white (no transition) when the stale nodes are swept first, so a dark program does not flash white.
- `create` for an id that exists: reuse the node when `type` matches (apply props with
  transitions, so shapes glide from old state to new), otherwise replace the element.
  Mark the id as fresh (delete from `staleIds`).
- Stale nodes are swept (removed, `staleIds = null`) on `error`, `end`, `status finished|crashed`
  after a `run`. While frames are still arriving the sweep is gentler, because the host can flush
  a frame in the middle of a long setup loop and old nodes not yet re-created would vanish and
  pop back without a transition:
  - after each `frame`, stale ids **lower than the highest id mentioned so far in this run** are
    removed at once (ids are handed out in creation order, so they will never be created);
  - stale ids above that stay for a grace period (300 ms) that starts at the first `frame` after
    the `run` that leaves some stale nodes; when it ends, everything still stale is removed.
  A setup that takes longer than the grace period and creates fewer objects than before may still
  flicker once; that is a known, accepted limitation. Re-running an unchanged script causes no
  flicker, and objects the program no longer creates disappear within ~300 ms.
- The stale background is reset to white at the first `frame` (or boundary), as before.
- `snapshot`: clear everything, rebuild without transitions.
- Coordinate mapping for messages: ignore frames whose `run` is older (messages are ordered per
  SSE connection, so this only matters across reconnects; snapshot resolves it).

## Input

- **Click:** `pointerdown`... use `click` on the SVG. Convert with
  `svg.getScreenCTM().inverse()` to viewBox coordinates, then logical `x = round(vx)`,
  `y = round(-vy)`. `target` = `data-id` of the nearest ancestor `[data-id]` of `event.target`
  inside `#shapes`, else `null`. Ignore clicks outside the 800x600 canvas rectangle.
  `POST /event` `{"t":"click","x","y","target"}` with `fetch` (keepalive), fire and forget.
- **Keys:** `keydown` on `window`, ignore when `ctrlKey/altKey/metaKey`. Ignore (do not forward, do
  not `preventDefault`) when the event target is inside the console panel (the console body is
  focusable so its keyboard scrolling works) or is an interactive control (input, textarea,
  select, button, link, summary, contenteditable): those keys belong to the browser. Otherwise send
  `{"t":"key","key": e.key === " " ? "Space" : e.key}` and `preventDefault()` for arrows and Space
  so the page doesn't scroll. Send `repeat` events too. Clicking Restart/Clear/the console toggle
  with the mouse blurs the button so later keys still reach the program; clicking the canvas moves
  focus out of the console.
- Events are only sent while state is `running`.
- Cursor: `pointer` over shapes whose element has a click handler is **not** known to the
  browser; keep the default cursor.

## Testability hooks

- `document.body.dataset.state` = current lifecycle state; `document.body.dataset.run` = run number;
  `document.body.dataset.ready` is set after the first message (the canvas is hidden until then).
- Every shape group has `data-id` and `data-type`; `#console` holds the text; the error panel
  has `id="error-panel"` (absent or `hidden` when no error); status badge `id="status"`.
- `window.__playground` exposes `{state, nodes}` read-only for debugging (not relied on by users).

## Files

`index.html` (structure + inline SVG skeleton, links `/static/style.css`, `/static/app.js`);
`app.js` (~800 lines max, one plain script, sections: connection, state, rendering, console, error panel, input);
`style.css`. Browser tests in `engine/tests/browser/` use a **fake host** (a tiny stdlib HTTP/SSE
server defined in that folder that serves `static/` and plays scripted messages) driven by
Playwright, so WP-C is testable without WP-B.
