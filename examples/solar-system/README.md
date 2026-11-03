# Solar System

Six planets go round the Sun, and the Earth has a Moon. The view is from high above, in deep
space. Press **G** to show a grid and the axes, and press **G** again to hide them.

```sh
./run.sh examples/solar-system/main.py
```

## What it shows

- **Lists and dictionaries**: every planet is a dictionary (`name`, `distance`, `size`,
  `color`, `speed`, `angle`), and all the planets live in one list called `planets`.
- **Loops**: a `for` loop makes all the planet shapes, and a `while True:` loop moves them.
- **Functions**: `orbit(distance, angle)` turns "how far" and "which direction" into an `x` and
  a `y` with `math.cos` and `math.sin`.
- **Animation**: change `x` and `y` a tiny bit, then `wait(0.03)`, over and over.
- **Events**: `on_key` runs `key_pressed` for every key you press. It happens inside `wait()`.
- **Showing and hiding**: `grid.hide()` at the start, and `grid.visible = not grid.visible` when
  you press **G**.
- **Names**: `name="Earth"` lets `get("Earth")` find the Earth again later, for the Moon.

## Try this

1. **Faster, slower.** Change the `speed` of Mars. What happens with a speed of `-1`?
2. **A new planet.** Add a dictionary for "Neptune" to the list. Pick a `distance`, a `size`
   and a `color`. Does it stay inside the picture?
3. **Your own colours.** Change the `color` of the Sun, the planets and the background in
   `canvas(background=...)`. Try `"#ffffff"` for a bright day, or `"black"`.
4. **Another moon.** Make a second moon that goes round Jupiter. Make it go the other way!
5. **Press a different key.** Add `if key == "r":` to `key_pressed` and make the Sun turn red.
