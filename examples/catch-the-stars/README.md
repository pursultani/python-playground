# Catch the Stars!

A small game with a clear start and a clear end. Move the rocket with the **left and right
arrow keys** to catch the falling stars, or **click a star** to pop it for bonus points. After
30 seconds the game says *Game over!*, prints your score, and the program finishes.

```sh
./run.sh examples/catch-the-stars/main.py
```

Click on the page once if your keys do not seem to arrive.

## What you can learn from it

| Idea | Where to look in `main.py` |
|---|---|
| **Variables and constants** | `GAME_SECONDS`, `STEP`, `score`: names at the top are easy to change |
| **A class** | `class Star(Text)`: a new kind of `Text` with its own `speed` and its own `fall()` |
| **A list** | `stars = []` remembers every star on the screen (`append`, `remove`) |
| **Functions** | `add_points`, `key_pressed`, `touches_player`: small jobs with a name |
| **A loop** | `while time.time() < end_time:` is the game loop; each trip is one "tick" |
| **Events** | `on_key(key_pressed)` for the keyboard, `self.on_click(self.pop)` for clicks |
| **Randomness** | `random` decides where stars appear and how fast they fall |
| **Program lifecycle** | Handlers only run inside `wait()`. When the loop ends there is no more `wait()`, so the program finishes and the page says *Program finished ✓* |

## Try this

1. **Longer or shorter game.** Change `GAME_SECONDS` to `10` for a quick round, or `60` for a
   marathon.
2. **More stars.** Make `STAR_CHANCE` bigger (`0.15`). What about `0.01`?
3. **Bigger rewards.** Change `POINTS_CLICK` so that popping a star is worth `5` points.
   Is clicking now better than catching?
4. **A new kind of star.** Make a `class BadStar(Star)` that shows `"💣"` and takes points
   away. Hint: give it its own `__init__`, call `super().__init__()`, then set
   `self.text = "💣"`. Then in the loop, sometimes create a `BadStar()`.
5. **Faster and faster.** Make the stars fall faster as time goes by, for example by adding
   to each new star's `speed` depending on how much time has passed.
6. **Your own look.** Change the colours, the rocket's size, or the `canvas(background=...)`.
