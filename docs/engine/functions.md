# Functions

Three small helpers. The two that handle clicks and keys are on the [Events](events.md) page.

## Change the background

`canvas(background=...)` sets the colour of the canvas. It only changes the background: your
shapes stay where they are. Call it again whenever you like.

```python
canvas(background="midnightblue")
Circle(color="gold")
```

::: core.canvas

## Pause and show

A program can run very fast. `wait(seconds)` pauses it, so you can see things move. While it
waits it also **shows every change** and **runs your click and key handlers**
(see [Events](events.md)).

```python
ball = Circle(-300, 0)
for step in range(60):
    ball.x += 10
    wait(0.03)        # about 30 frames per second
```

`wait(0)` shows the changes and handles clicks without pausing at all.

::: core.wait

## Find an object

Give an object a `name` when you make it, and find it again anywhere in your program with
`get`. Names must be different from each other. When you [`remove()`](shapes.md#every-object)
an object its name can be used again.

```python
Circle(name="ball")
Rectangle(100, 0, name="box")

def go_right():
    get("ball").x += 50
    get("box").color = "red"

go_right()
```

If no object has that name, you get an error that suggests a close match if there is one:
`No object is named 'bal'. Did you mean 'ball'?`

::: core.get
