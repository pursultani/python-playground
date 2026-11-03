# Guides

Guides help you **read positions** on the canvas. They are drawn **behind** every shape, they
have no position of their own, and clicks go straight through them.

A new canvas has no guides. Make the ones you want:

```python
Grid()
Axis()
Circle(100, 50, radius=20, color="tomato")
```

Now you can see that the circle is at `x = 100`, `y = 50`.

You can make several guides, give them names, and hide or remove them like any other object
(see [Every object](shapes.md#every-object)):

```python
grid = Grid(size=25, color="gainsboro", name="grid")
Axis(size=100, labels=False)
grid.hide()
```

::: core.Grid

::: core.Axis
