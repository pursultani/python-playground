# Spec: examples

Owner: WP-X. Two showpiece programs written **exactly as a student would write them**: no
imports of the engine, plain Python, readable by a motivated 10-12 year old, heavily but
tastefully commented (these are teaching material: comments explain *what and why* in
child-friendly words). Each lives in `examples/<name>/` with:

- `main.py`
- `README.md`: what it shows, which concepts (variables, loops, lists, dicts, functions, OOP,
  events...), what to try changing (3-5 "try this" challenges)
- `pyrightconfig.json`: `{"stubPath": "../../engine/typings"}`

Both must run with `./run.sh examples/<name>/main.py`, look great, and use only the API in
`api.md` (+ `import math`/`import random` from the standard library, which is fine).
Use color for delight: pick a pleasant palette, a background via `canvas(background=...)`.
No file may exceed ~120 lines of code.

## 1. `examples/solar-system/`

An animated solar system seen from above.

- Sun (large yellow-orange circle with title `"Sun"`), planets orbiting at different speeds
  and distances, a moon orbiting one planet. Dark space background (`canvas(background="#0b1026")`);
  faint orbit rings are optional (circles cannot be unfilled in v1, so skip or fake with thin
  `Circle`s of low `opacity` behind; keep it simple).
- A list of dictionaries describes the planets (name, distance, size, color, speed); a loop
  creates the shapes; a function computes position from the angle (`math.cos`/`math.sin`);
  a `while True:` loop with `wait(0.03)` animates. Titles show planet names. Optionally a
  `Grid()`/`Axis()` hidden by default and toggled by a key press (`on_key`: `g`), which also
  demonstrates `show()`/`hide()` and `wait()` as the event loop.
- Must never raise errors, runs indefinitely (state stays `running`).

## 2. `examples/catch-the-stars/`

A small keyboard-and-click game with a clear start and end.

- `Triangle` or `Rectangle` player at the bottom moved with `ArrowLeft`/`ArrowRight` via `on_key`
  (clamped to the canvas). Stars are `Text("⭐")` objects falling from random x positions.
- `class Star(Text)` (OOP: constructor, `fall()` method, `speed` attribute); stars kept in a list;
  caught when overlapping the player (simple distance test), missed when below the floor;
  score `Text` at top (updates live). Clicking a star pops it for a bonus point (`Star.on_click`).
- Game lasts a fixed time (e.g. 30 s of `wait(0.03)` ticks), then shows a big `Text("Game over!
  Score: N")`, calls `print` with the final score, and the **script ends**, so the browser shows
  `Program finished ✓` (this demonstrates the program lifecycle).
- Uses a `while` loop with `wait`, a list, a class, functions, `random`, `print`, `on_key`,
  `on_click`.

## Verification (WP-X)

For each example: run it through the real stack (Playwright against `./run.sh ... --no-browser
--port <free>` or the supervisor in-process), assert expected behavior (see below), and look at a
screenshot (temp dir only). Add `engine/tests/e2e/test_examples.py` **only if WP-I has not yet
created it; otherwise append your tests in `engine/tests/e2e/test_example_<name>.py`**.

Assertions:

- solar-system: status becomes `running`; at least N `data-type=circle` shapes exist; after 1 s
  at least one planet's transform has changed; no error panel; pressing `g` toggles a grid
  node's visibility (if implemented).
- catch-the-stars: status `running`; player moves when `ArrowLeft` is pressed; stars exist;
  after the game time (patch via env var `PLAYGROUND_FAST=1` that the example does **not** read:
  instead make the duration a variable at the top of `main.py` and let tests run a temp copy with
  a short duration) status becomes `finished`, the "Game over" text is present, console
  contains the final score, no error panel.
