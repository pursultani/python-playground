# Engine reference

Everything on this page is **already loaded** in your program. You never import it.

## The canvas

```text
                    y = 300
                       │
                       │
   x = -400 ───────────┼─────────── x = 400
                       │ (0, 0)
                       │
                    y = -300
```

- The canvas is **800 wide, 600 tall**.
- `(0, 0)` is the **middle**. `x` grows to the **right**, `y` grows **up**.
- Angles are in **degrees**, turning **counter-clockwise**.
- Every run starts with a **blank white canvas**.

## Everything you can use

| Name | Kind | What it does |
|---|---|---|
| [`Circle`](shapes.md#core.Circle) | shape | A circle. `Circle(100, 50, radius=40)` |
| [`Rectangle`](shapes.md#core.Rectangle) | shape | A rectangle centred on its position. |
| [`Triangle`](shapes.md#core.Triangle) | shape | A triangle with its point up. |
| [`Line`](shapes.md#core.Line) | shape | A straight line from `(x, y)` to `(x2, y2)`. |
| [`Text`](shapes.md#core.Text) | shape | Words or emoji. `Text("Hello", 0, 100)` |
| [`Shape`](shapes.md#core.Shape) | base class | What every shape has in common. You never make one directly. |
| [`Grid`](guides.md#core.Grid) | guide | Lines behind your shapes that help you read positions. |
| [`Axis`](guides.md#core.Axis) | guide | The x and y axes with numbers. |
| [`canvas`](functions.md#core.canvas) | function | Set the background colour. |
| [`wait`](functions.md#core.wait) | function | Pause, show the changes, and handle clicks and keys. |
| [`get`](functions.md#core.get) | function | Find an object by its `name`. |
| [`on_click`](events.md#core.on_click) | function | Call your function when the canvas is clicked. |
| [`on_key`](events.md#core.on_key) | function | Call your function when a key is pressed. |

`print` is the normal Python `print`. What it prints shows up in the console under the canvas.

## Properties

Everything you draw has **properties**: `x`, `y`, `color`, `radius` and so on. Give them when
you create the object, read them, or change them whenever you like:

```python
ball = Circle(0, 0, radius=40, color="orange")   # give them at the start
ball.color = "tomato"                            # change one later
print(ball.radius)                               # read one
```

Changing a property updates the canvas right away. Use [`wait()`](functions.md#core.wait) to
slow things down so you can watch them move.

Properties check what you give them. A wrong kind of value, or a property that does not exist,
raises an error that explains the problem. See [Friendly errors](errors.md).

## Colours

Anything that takes a colour accepts:

- a name: `"red"`, `"steelblue"`, `"midnightblue"`
- a code: `"#ff8800"`
- `"rgb(255, 136, 0)"` or `"hsl(30, 100%, 50%)"`

## How shapes and guides relate

Shapes and guides are both **objects**. Every object has `name`, `visible`, `opacity`, `show()`,
`hide()` and `remove()`: see [Every object](shapes.md#every-object). Shapes also have a position,
a colour and `on_click`. Guides are drawn behind all shapes and cannot be clicked.
