# Events

An **event** is something the person at the keyboard does: click the canvas, or press a key.
Your program says which function should run for each kind of event. That function is a
**handler**.

```python
ball = Circle(color="gold")

def jump(x, y):
    ball.x = x
    ball.y = y

on_click(jump)

while True:
    wait(0.05)
```

Click anywhere on the canvas and the ball jumps there.

## The event loop

Handlers do **not** run by magic. They run **only inside `wait()`**. Each time your program
reaches `wait(...)`, Python checks whether any clicks or keys happened since last time, calls
your handlers for them in the order they happened, then carries on waiting.

That is why a program that reacts to the user ends with a loop:

```python
while True:
    wait(0.05)
```

Think of it as the program saying "now I'll sit here and listen". Without the loop the last
line runs, the program **finishes**, and later clicks and key presses are ignored. The page
says *Program finished ✓*.

!!! warning "Don't forget to wait"
    A program that never reaches `wait()` never listens. If your handler seems to do nothing,
    check that your program keeps waiting.

If a handler makes a mistake, the program stops with an error that shows the handler's line.

## What your handler receives

Your function can take **as many values as it wants, up to what the event offers**:

| Event | Values given | Functions that work |
|---|---|---|
| click | `x`, `y` | `def hit():` or `def hit(x):` or `def hit(x, y):` |
| key | `key` | `def pressed():` or `def pressed(key):` |

If your function asks for more than the event gives, you get an error when you register it,
with a plain explanation.

Registering a handler **replaces** the one you had before. Pass `None` to remove it:

```python
on_click(None)
```

## Clicks

Your handler gets the canvas position of the click: `x` and `y`, rounded to whole numbers.

`on_click(handler)` listens for clicks **anywhere on the canvas**:

::: core.on_click
    options:
      heading_level: 3

### Clicking a shape

Every shape has its own `on_click`. It only fires for clicks **on that shape**
([reference](shapes.md#core.Shape.on_click)):

```python
star = Text("⭐", 0, 0, size=80)
score = Text("0", 0, 200)
clicks = 0

def caught():
    global clicks
    clicks += 1
    score.text = clicks

star.on_click(caught)

while True:
    wait(0.05)
```

If shapes overlap, the one on top gets the click. If that shape has no handler of its own, the
click passes through to the handler you gave `on_click(...)` for the canvas (if any).

## Keys

`key` is the name of the key that was pressed:

| Key | `key` is |
|---|---|
| a letter or digit | `"a"`, `"A"` (with Shift), `"7"` |
| an arrow | `"ArrowLeft"`, `"ArrowRight"`, `"ArrowUp"`, `"ArrowDown"` |
| the space bar | `"Space"` |
| other keys | `"Enter"`, `"Escape"`, ... |

Holding a key down sends it again and again. Combinations with `Ctrl`, `Alt` or `Cmd` are not
passed on, so your browser shortcuts keep working. Click the page first if your keys do not
seem to arrive.

::: core.on_key
    options:
      heading_level: 3
