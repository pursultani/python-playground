# Getting started

## What you need

- **Python 3.10 or newer** (`python3 --version` tells you).
- **A web browser.**
- **A text editor.** [VS Code](https://code.visualstudio.com/) with its Python extension is
  the friendliest, because it can suggest names and explain them as you type (see
  [Set up VS Code](#set-up-vs-code) below). Any editor works.

Not sure everything is ready? Run the checker. It only looks, it never installs anything:

```sh
./install.sh
```

## Run an example

```sh
./run.sh examples/solar-system/main.py
./run.sh examples/catch-the-stars/main.py
```

`./run.sh` on its own lists the examples. Two options are sometimes handy:

| Option | What it does |
|---|---|
| `--port 9000` | Use this port instead of the default (8765). |
| `--no-browser` | Don't open the browser. Open the address printed in the terminal yourself. |

## Start your own program

```sh
./run.sh new my-program
./run.sh my-program/main.py
```

The first command makes a folder with a short starter `main.py` and the files that make your
editor helpful. It will not touch a folder that already has files in it. The second command
runs the program and opens your browser.

Now edit `main.py` and save (`Ctrl+S`, or `Cmd+S` on a Mac). The browser page notices the
change and **runs your program again from the top**. Stop everything with `Ctrl+C` in the
terminal.

## What the page shows

```text
┌──────────────────────────────────────────────────────────┐
│ ▶ Python Playground      main.py      ● Running…  Restart│
├──────────────────────────────────────────────────────────┤
│                   the 800 x 600 canvas                   │
├──────────────────────────────────────────────────────────┤
│ ▾ Console                                          Clear │
│   Hello! I made a ball.                                  │
└──────────────────────────────────────────────────────────┘
```

- **The canvas** is where your shapes appear. It scales to fit the window.
- **The console** shows everything you `print`.
- **The status badge** tells you what your program is doing right now (next section).
- **Restart** runs your program again without saving.
- **A red error card** appears over the canvas when something goes wrong. It shows the line
  of code that caused it. See [Friendly errors](engine/errors.md).

If the page says *Disconnected: waiting for the playground…*, the terminal command has stopped.
Run it again and the page reconnects by itself.

## A program starts, and a program ends

Your program runs from the first line to the last line, like a recipe. The badge shows where
it is:

| Badge | Meaning |
|---|---|
| Starting… | Python is getting ready. |
| Running… | Your program is executing lines. |
| Program finished ✓ | The last line ran. **The drawing stays on the canvas.** |
| Stopped by an error ✗ | Something went wrong. Read the red card. |

The program below ends after the last line, so the badge says *Program finished*:

```python
ball = Circle()
ball.color = "orange"
print("Done!")
```

### The event loop: keep the program alive

Clicks and key presses are only handled **while your program is running**, and only inside
[`wait()`](engine/functions.md). So a program that reacts to the user keeps itself alive with a
loop:

```python
ball = Circle(color="gold")

def pressed(key):
    if key == "ArrowRight":
        ball.x += 10

on_key(pressed)

while True:
    wait(0.05)
```

`wait(0.05)` pauses for a twentieth of a second, shows the latest changes in the browser, and
runs your `pressed` function for every key that was pressed meanwhile. Read more in
[Events](engine/events.md).

## No `import` needed

Normally Python code starts with imports. Here the whole API is already loaded, so
`Circle(...)` just works. Python's own helpers still work the usual way:

```python
import random

Circle(random.randint(-300, 300), 0)
```

`input()` does not work in Python Playground (it stops the program with an error). Use
`on_click` and `on_key` instead. See [Events](engine/events.md).

## Set up VS Code

`./run.sh new my-program` already created everything your editor needs inside the folder:

- `main.py` is your program.
- `typings/__builtins__.pyi` is a "dictionary" of the Playground names. It lets the editor
  suggest `Circle`, show help when you hover over it, and spot typos like `ball.colour`.
- `pyrightconfig.json` tells the editor where to find that dictionary, and to mark unknown
  names as errors.
- `.vscode/settings.json` holds the same settings for VS Code's Python tools.

To use it:

1. Install **VS Code** and its **Python** extension (this includes Pylance).
2. Choose **File > Open Folder** and open the `my-program` folder itself, the one that contains
   `pyrightconfig.json`.
3. Open `main.py` and start typing `Cir`. The editor suggests `Circle`. Hover over a name to
   read its help, or type `(` to see what it accepts.

!!! tip "Why no import?"
    When your program runs, the Playground puts all its names into your program for you. The
    `__builtins__.pyi` file tells the editor the same story: it declares them like Python's
    own built-in names (`print`, `len`), which never need an import either. A name that is not
    in the dictionary (for example a misspelled `Cirlce`) is still reported as undefined.

If the editor underlines `Circle` as undefined, you probably opened a different folder.
Reopen the folder that contains `pyrightconfig.json` and `typings/`.

Teachers: the example folders include their own `pyrightconfig.json`, so you can open any
example folder in VS Code and get the same help.

## When something looks wrong

| You see | Try |
|---|---|
| A red error card | Read the message. It says what is wrong and often how to fix it. |
| Nothing on the canvas | Did you create a shape? Is it inside x from -400 to 400 and y from -300 to 300? Add `Grid()` to see where things are. |
| The page does not change when you save | Is the program still running in the terminal? Press **Restart** on the page. |
| Clicks and keys do nothing | Does your program have `while True: wait(...)` at the end? |
