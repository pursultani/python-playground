# Friendly errors

Everybody makes mistakes. Python Playground tries to make them useful.

When your program stops because of an error, a red card appears over the canvas and the badge
says *Stopped by an error ✗*. The card looks like this:

```text
⚠ ValueError
radius must be more than 0, but got -5

File main.py, line 4

  2 | ball = Circle()
  3 | ball.color = "orange"
> 4 | ball.radius = -5
  5 | print("done")
```

1. **What kind of mistake it is** and a sentence saying what happened.
2. **Where**: the file and line number.
3. **The code**, with the exact line marked.

Your shapes stay on the canvas, so you can see how far the program got. Fix the file, save,
and the card goes away.

## Read the message

Messages say what they **expected** and what they **got**:

| You wrote | The message |
|---|---|
| `Circle(radius="big")` | `radius must be a number, but got 'big'` |
| `Circle(radius=-5)` | `radius must be more than 0, but got -5` |
| `ball.opacity = 5` | `opacity must be between 0 and 1, but got 5` |
| `ball.color = "gren"` | `color must be a color name like "red" or a code like "#ff8800", but got 'gren'. Did you mean 'green'?` |
| `Grid(style="dash")` | `style must be one of 'solid', 'dashed', 'dotted', but got 'dash'. Did you mean 'dashed'?` |
| `wait(-1)` | `seconds must be 0 or more, but got -1` |

## Typos get a hint

The most common mistake is a misspelled property. Python Playground catches it, and tells you
what it thinks you meant:

| You wrote | The message |
|---|---|
| `ball.colour = "red"` | `Circle has no property 'colour'. Did you mean 'color'?` |
| `Circle(colour="red")` | `Circle() got an unknown property 'colour'. Did you mean 'color'?` |
| `ball.sho()` | `Circle has no property 'sho'. Did you mean 'show'?` |
| `get("bal")` | `No object is named 'bal'. Did you mean 'ball'?` |

Your own classes can have any attributes you like (`self.speed = 10`). The check only steps in
when a new name looks almost the same as a real property. Plurals such as `self.colors` or
`self.names` (a list of colours, a list of names) are always fine.

## Other mistakes you might meet

| You wrote | The message |
|---|---|
| `Circle(1, 2, 3)` | `Circle() takes at most 2 values without a name (x, y). Give the others by name, like radius=...` |
| `Text("hi", title="x")` | `Text() got an unknown property 'title'.` |
| Two shapes with `name="a"` | `There is already an object named 'a'. Names must be different.` |
| `on_click(5)` | `on_click needs a function, but got 5. Give the function's name without brackets, like on_click(my_function).` |
| `Circle(10, x=5)` | `x was given twice: once by position and once by name.` |
| `Grid(50)` | `Grid() needs names for its values, like Grid(size=50).` |
| `Text(0, 100, "hi")` | `Text starts with its words: Text("hi", 0, 100)` |
| A `super().__init__()` call twice in your class | `super().__init__() was called twice. Call it only once, at the start of __init__.` |
| Thousands of shapes in a loop | `Too many shapes (5000). Did you forget to remove() old ones?` |
| `input()` | An `EOFError` saying that `input()` does not work in the playground. Use `on_click` or `on_key` to hear from the player instead. |
| `Shape()` | `Shape can't be used directly. Use Circle, Rectangle, Triangle, Line or Text instead.` |

## Python's own errors

Mistakes that are not about shapes (a misspelled variable, a missing bracket) show Python's
own message in the same red card. Python often suggests a fix too:

| Kind | Typical cause |
|---|---|
| `NameError` | A name that does not exist: a typo, or used before it was made. |
| `SyntaxError` | Something is missing or misplaced: a bracket, a colon, a quote. |
| `IndentationError` | A line is lined up wrongly. Lines inside a loop or `def` need the same number of spaces. |
| `TypeError` | A value of the wrong kind, for example adding a number to text. |
| `ZeroDivisionError` | Dividing by zero. |

The card only shows **your** code, never the machinery inside Python Playground.

## Errors in handlers

If a click or key handler makes a mistake, the program stops too and the card points at the
line inside the handler. The card also lists the line of your program that was waiting at the
time.

## The program stopped unexpectedly

If you see *The program stopped unexpectedly*, the program ended without telling the page why.
Press **Restart**. If it keeps happening, ask your teacher.
