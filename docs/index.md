# Python Playground

Write a few lines of Python. Save the file. Watch circles, rectangles and words come alive in
your browser.

Python Playground is a tiny framework for learning to program. You type plain Python in any
text editor, run one command, and a browser tab shows what your program draws, what it prints
and, when you make a mistake, a friendly message that points at the exact line.

You never write `import`. Everything you need (`Circle`, `Text`, `wait`, ...) is ready to use.

## Try it in 60 seconds

You need Python 3.10 or newer and a web browser. Open a terminal in the project folder and run:

```sh
./run.sh examples/solar-system/main.py
```

A browser tab opens. Edit the file, save it, and the page restarts your program by itself.
Press `Ctrl+C` in the terminal to stop.

## Your first program

```sh
./run.sh new my-program
./run.sh my-program/main.py
```

Open `my-program/main.py`, change it to this, and save:

```python
Grid()

ball = Circle(0, 0, radius=60, color="tomato")
print("Hello! I made a ball.")

wait(1)
ball.x = 150
```

You get a red ball in the middle of a grid. After one second it slides to the right, and the
console under the canvas says `Hello! I made a ball.`

The canvas is **800 wide and 600 tall**. The point `(0, 0)` is in the **middle**, `x` grows to
the right and `y` grows **up**, like on a maths graph.

## Where to go next

| I want to... | Read |
|---|---|
| Set things up and learn how the page works | [Getting started](getting-started.md) |
| See every shape, with what it can do | [Shapes](engine/shapes.md) |
| Draw a grid or axes to read positions | [Guides](engine/guides.md) |
| Change the background, pause, find an object | [Functions](engine/functions.md) |
| React to clicks and key presses | [Events](engine/events.md) |
| Understand the messages when something goes wrong | [Friendly errors](engine/errors.md) |
| See how it is built (for teachers and developers) | [Architecture](developer/architecture.md) |
