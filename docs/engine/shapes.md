# Shapes

Shapes are what you draw. Every shape has a position `(x, y)` at its **centre**, a `color`, and
a few things that are special to it, like a circle's `radius`.

```python
sun = Circle(0, 0, radius=60, color="gold", title="Sun")
box = Rectangle(-200, -100, width=120, height=60, color="seagreen")
roof = Triangle(200, -100, width=120, height=80, color="firebrick")
rope = Line(-200, 100, 200, 100, width=5, color="slategray")
hello = Text("Hello!", 0, 200, size=48, color="purple")
```

## Pick a shape

| Shape | Extra properties | Notes |
|---|---|---|
| [`Circle`](#core.Circle) | `radius` | |
| [`Rectangle`](#core.Rectangle) | `width`, `height` | Centred on `x, y`. |
| [`Triangle`](#core.Triangle) | `width`, `height` | Point up, centred on `x, y`. |
| [`Line`](#core.Line) | `x2`, `y2`, `width` | From `(x, y)` to `(x2, y2)`. **Cannot be rotated.** |
| [`Text`](#core.Text) | `text`, `size` | Words or emoji. **Has no `title`.** |

## Positions and names of arguments

The first values can be written **without** their names: `Circle(100, 50)` means
`Circle(x=100, y=50)`. `Text` starts with its words: `Text("Hi", 0, 100)`. `Line` starts with
`x, y, x2, y2`. Everything else is given **by name**:

```python
Circle(100, 50, radius=40, color="orange")
```

## Change a shape later

Every property can be changed after the shape exists:

```python
ball = Circle(-300, 0, color="orange")

for step in range(60):
    ball.x += 10
    ball.rotation += 6
    wait(0.03)
```

## Hide, show and remove

```python
ghost = Circle(opacity=0.3)   # see-through
ghost.hide()                  # not drawn, but still there
ghost.show()
ghost.remove()                # gone for good
```

## Give a shape a name

A `name` is a secret label that you can look up later with [`get`](functions.md#core.get):

```python
Circle(name="ball")
get("ball").color = "red"
```

## Make your own kind of shape

Subclass a shape to give it extra attributes and methods:

```python
class Player(Circle):
    def __init__(self):
        super().__init__(x=0, y=-200, color="orange", name="player")
        self.speed = 10

    def move_left(self):
        self.x -= self.speed

player = Player()
player.move_left()
```

Always call `super().__init__(...)` first. Your own attributes (`speed`) are fine, but a
misspelling of a real property (`self.colour`) is still caught.

## Every object

Shapes and [guides](guides.md) share these properties and methods.

::: core.shapes.Object.name
    options:
      heading_level: 3

::: core.shapes.Object.visible
    options:
      heading_level: 3

::: core.shapes.Object.opacity
    options:
      heading_level: 3

::: core.shapes.Object.show
    options:
      heading_level: 3

::: core.shapes.Object.hide
    options:
      heading_level: 3

::: core.shapes.Object.remove
    options:
      heading_level: 3

Every shape also has the properties of [`Shape`](#core.Shape) below. You never create a
plain `Shape`: use one of the shapes that follow. `Line` has no `rotation` and `Text` has no
`title`.

::: core.Shape
    options:
      show_signature: false
      merge_init_into_class: false
      members: [x, y, color, rotation, title, on_click]

::: core.Circle

::: core.Rectangle

::: core.Triangle

::: core.Line

::: core.Text
