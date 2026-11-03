# Spec: public Python API

Owner: WP-A. This is what students type. Everything listed in `core.__all__` is pre-loaded into
the student's script (no `import`). `core.namespace()` returns `{name: obj for name in __all__}`.

## Canvas and coordinates

- Logical canvas: **800 x 600**, origin **(0, 0) at the centre**, **+x right, +y up** (maths graph).
  Visible range: x in [-400, 400], y in [-300, 300].
- Every run starts with a **blank white canvas** and no objects.
- Angles (`rotation`) are in **degrees, counter-clockwise** (maths convention).

## Public names (`__all__`)

Shapes: `Circle`, `Rectangle`, `Triangle`, `Line`, `Text`, `Shape` (base class, for subclassing).
Guides: `Grid`, `Axis`.
Functions: `canvas`, `wait`, `get`, `on_click`, `on_key`.

`print` is the normal built-in; its output goes to the browser console.

## Base behavior shared by all objects (`Grid`, `Axis`, and every shape)

| Member | Kind | Default | Notes |
|---|---|---|---|
| `name` | property, `str` or `None` | `None` | Invisible. Unique among live objects. Used by `get(name)`. |
| `visible` | property, `bool` | `True` | `show()` / `hide()` set it. |
| `opacity` | property, number 0..1 | `1` | |
| `show()` | method | | Sets `visible = True`. |
| `hide()` | method | | Sets `visible = False`. |
| `remove()` | method | | Deletes from the canvas for good and releases `name`. Later property changes are ignored silently. |
| `__repr__` | | | e.g. `Circle(x=0, y=0, name='ball')`: the class name plus the properties that differ from defaults (always `x`/`y` for shapes). Useful with `print`. |

Property assignment rules:

- Reading returns exactly what was assigned (no coercion). Numbers: `int`/`float` accepted;
  `bool`, `str`, `None`, NaN and infinities rejected.
- Assignment validates, stores, and queues a screen update (see `protocol.md`).
- Invalid values raise `TypeError` (wrong kind) or `ValueError` (right kind, bad value) with a
  plain message that names the property and shows what was received, for example
  `x must be a number, but got 'ten'` and `opacity must be between 0 and 1, but got 5`.
- **Unknown property** on a built-in class raises `AttributeError`:
  `Circle has no property 'colour'. Did you mean 'color'?` (omit the hint if nothing is close).
  Same for unknown constructor keywords (`TypeError`: `Circle() got an unknown property 'colour'. Did you mean 'color'?`).
- **Subclasses** (`class Player(Circle):`) may add their own attributes freely. Names starting
  with `_` are always free. A new attribute whose name is a close match (difflib cutoff 0.85) to
  a real property is still rejected with the hint above. **Exception:** a name that is exactly a
  property name plus `s` or `es` (`self.colors`, `self.names`, `self.titles`) is always free,
  because students keep lists with those names.
- Constructor arguments are **keyword-only except** the leading positional ones listed per class.
  Every constructor accepts every property of the class as a keyword.
- Constructor mistakes get plain messages: giving a value both by position and by name
  (`Circle(10, x=5)`) says `x was given twice: once by position and once by name.`; positional
  values for a class that takes none (`Grid(50)`, `Axis(100)`) say
  `Grid() needs names for its values, like Grid(size=50).`; `Text(0, 100, "hi")` (position first)
  says `Text starts with its words: Text("hi", 0, 100)`.
- **Live object cap:** at most **5000** objects (shapes and guides) may be alive at once. Creating
  another raises `RuntimeError`: `Too many shapes (5000). Did you forget to remove() old ones?`
  `remove()` frees capacity. This keeps a runaway `while True: Circle()` from freezing the page.
- Creating an object queues a `create` operation; the object appears on the next frame.

### `Shape(Object)` common properties

| Property | Type | Default | Meaning |
|---|---|---|---|
| `x`, `y` | number | `0` | Centre of the shape (start point for `Line`). |
| `color` | colour | `"steelblue"` (`Text`: `"black"`, `Line`: `"black"`) | Fill colour (stroke for `Line`). |
| `rotation` | number (degrees) | `0` | About the shape's centre. **Not available on `Line`.** |
| `title` | `str` | `""` | Visible label drawn at the centre of the shape. **Not available on `Text`.** |

Positional constructor arguments: `x`, `y` first for every shape (`Circle(100, 50)`);
`Text(text, x, y)`; `Line(x, y, x2, y2)`.

Method: `on_click(handler)`: see Events. Passing `None` removes the handler.

### Concrete shapes

| Class | Extra properties (default) | Notes |
|---|---|---|
| `Circle` | `radius` (50) > 0 | |
| `Rectangle` | `width` (100) > 0, `height` (60) > 0 | Centred on `x, y`. |
| `Triangle` | `width` (100) > 0, `height` (100) > 0 | Isosceles, apex up, bounding box centred on `x, y`. |
| `Line` | `x2` (100), `y2` (0), `width` (3) > 0, no `rotation`, ends rounded | Line from `(x, y)` to `(x2, y2)`; title at the midpoint. |
| `Text` | `text` (`""`, anything is converted with `str()`), `size` (32) > 0 (font size in canvas units) | Centred on `x, y`. No `title`. Emoji render in colour. |

`Shape` itself cannot be instantiated directly (`TypeError`: use Circle, Rectangle, ...). It is
exported so students can write `class Thing(Shape)` only if they define their own geometry later;
v1 does not support custom geometry. Docs recommend subclassing a concrete shape.

### `Grid` and `Axis` (guides)

Guides are objects with `name`, `visible`, `opacity`, `show()`, `hide()`, `remove()`.
They have **no** `x`, `y`, `rotation`, `title`, or `on_click`. They are drawn **behind all shapes**
and never receive clicks. Creating one shows it immediately. A canvas starts with none; the
student creates what they want (`Grid()`, `Axis()`). Creating several is allowed.

| Property | `Grid` default | `Axis` default | Meaning |
|---|---|---|---|
| `color` | `"lightgray"` | `"gray"` | Line colour. |
| `width` | `1` | `3` | Line thickness in canvas units. The axis is thicker than the grid by default. |
| `size` | `50` | `50` | Grid: distance between lines. Axis: distance between tick marks. Number > 0. |
| `style` | `"solid"` | `"solid"` | One of `"solid"`, `"dashed"`, `"dotted"`. |
| `labels` | n/a | `True` | Axis only: show tick numbers. |

Grid lines span the whole canvas and always include the lines through the origin (multiples of
`size`). Axis draws the x axis and y axis through the origin with tick marks every `size`.

## Functions

### `canvas(background="white")`

Sets the background colour of the canvas (colour validated like any `color`). It **only** changes
the background: shapes stay. Returns `None`. Called again later it updates the background live.

### `wait(seconds=0)`

Pauses the program for `seconds` (number >= 0; else `TypeError`/`ValueError` with a friendly
message). During the pause:

1. pending changes are flushed to the browser immediately,
2. queued events (clicks, keys) are dispatched to handlers **on the main thread, in arrival
   order**, then the wait continues until `seconds` have passed in total.

`wait(0)` flushes and dispatches pending events without sleeping. If a handler raises, the
exception propagates out of `wait()` and ends the program (the error shows the handler's line).
**Handlers run only inside `wait()`.** There is no hidden event loop: when the script ends, the
program is over and later events are ignored.

### `get(name)`

Returns the live object with that name. Unknown name raises `LookupError`:
`No object is named 'bal'. Did you mean 'ball'?` (hint only if close). Duplicate names raise
`ValueError` at creation or when `name` is assigned:
`There is already an object named 'ball'. Names must be different.` Removing an object frees its name.

### Events

```python
on_click(handler)        # clicks anywhere on the canvas
shape.on_click(handler)  # clicks on that shape
on_key(handler)          # key presses
```

- Each registration **replaces** the previous handler of the same kind; `None` clears it.
- Handlers must be callable (`TypeError: on_click needs a function, ...`).
- **Arity:** call with the documented arguments but only as many as the function accepts
  (`inspect.signature`; `*args` receives all). Click handlers: `(x, y)`; key handlers: `(key)`.
  So `def hit():`, `def hit(x):`, `def hit(x, y):` all work. Extra required parameters raise
  `TypeError` with a friendly message at registration time.
- **Click target:** the browser reports the topmost shape under the cursor. If that shape has a
  handler, only it is called. Otherwise the canvas-level handler is called (clicks pass through
  shapes without handlers). Coordinates are in logical canvas units, rounded to integers.
- **Keys:** `key` is the browser `KeyboardEvent.key` except space, which is `"Space"`.
  Examples: `"a"`, `"A"`, `"1"`, `"ArrowLeft"`, `"Enter"`, `"Escape"`, `"Space"`.
  Key repeats (holding a key) are delivered. Combinations with Ctrl/Alt/Meta are not forwarded.

## Subclassing (OOP lesson)

```python
class Player(Circle):
    def __init__(self):
        super().__init__(x=0, y=-200, color="orange", name="player")
        self.speed = 10          # free attribute

    def move_left(self):
        self.x -= self.speed
```

Must work: subclass attributes, methods, `super().__init__`, setting properties before
`super().__init__` is NOT required to work, but must not crash the engine with an unclear error
(raise `RuntimeError`: `Call super().__init__() before using properties`). Calling
`super().__init__()` a second time raises `RuntimeError` (`super().__init__() was called twice...`)
instead of leaving a ghost object on the canvas.

## Docstrings

Every public class, function, method and property has a Google-style docstring with an
`Example:` that runs inside the playground. Property docstrings go directly under the attribute
(attribute docstring) so `griffe` and the stub generator pick them up.

## Typing contract (for stubs and pyright)

Properties are declared in source as annotated class attributes initialised by the `prop()` factory,
which is typed to return `Any`:

```python
class Circle(Shape):
    radius: float = prop(50, positive_number)
    """Distance from the centre to the edge."""
```

so that `griffe` sees the public type (`float`) and pyright accepts the file. Colour properties are
annotated `str`. The generated stub (`engine/typings/__builtins__.pyi`) must be derivable from
source alone.
