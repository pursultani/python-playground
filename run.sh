#!/bin/sh
# Python Playground launcher. Plain POSIX sh: needs only python3 (3.10 or newer).
#
#   ./run.sh path/to/main.py [--port N] [--no-browser]   run a program
#   ./run.sh new <folder>                                create a new project
#   ./run.sh --help

set -eu

invoked=$0

# Find the folder this script lives in, even when called through a symlink.
self=$0
while [ -h "$self" ]; do
    link=$(readlink "$self")
    case $link in
        /*) self=$link ;;
        *) self=${self%/*}/$link ;;
    esac
done
case $self in
    */*) here=${self%/*} ;;
    *) here=. ;;
esac
ROOT=$(cd "$here" && pwd -P)

say() {
    printf '%s\n' "$*"
}

fail() {
    printf '%s\n' "$*" >&2
    exit 1
}

list_examples() {
    found=0
    for dir in "$ROOT"/examples/*/; do
        [ -f "${dir}main.py" ] || continue
        name=${dir%/}
        name=${name##*/}
        if [ "$PWD" = "$ROOT" ]; then
            say "  $invoked examples/$name/main.py"
        else
            say "  $invoked $ROOT/examples/$name/main.py"
        fi
        found=1
    done
    [ "$found" -eq 1 ] || say "  (no examples found yet)"
}

usage() {
    say "Python Playground"
    say ""
    say "Usage:"
    say "  $invoked path/to/main.py [--port N] [--no-browser]   run a program"
    say "  $invoked new <folder>                                create a new project"
    say "  $invoked --help                                      show this help"
    say ""
    say "Examples to try:"
    list_examples
    say ""
    say "Save your file and the browser page updates by itself. Press Ctrl+C here to stop."
}

find_python() {
    PYTHON=
    for candidate in python3 python3.15 python3.14 python3.13 python3.12 python3.11 python3.10; do
        command -v "$candidate" >/dev/null 2>&1 || continue
        if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' \
            >/dev/null 2>&1; then
            PYTHON=$candidate
            return 0
        fi
    done
    return 1
}

need_python() {
    find_python && return 0
    found=
    if command -v python3 >/dev/null 2>&1; then
        found=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null) || found=
    fi
    if [ -n "$found" ]; then
        say "Python Playground needs Python 3.10 or newer, but python3 here is version $found." >&2
    else
        say "Python Playground needs Python 3.10 or newer, but python3 was not found." >&2
    fi
    say "Run ./install.sh for help getting it, then try again." >&2
    exit 1
}

new_project() {
    if [ "$#" -ne 1 ] || [ -z "$1" ]; then
        say "Please give the new project a folder name, for example:" >&2
        say "  $invoked new my-first-program" >&2
        exit 2
    fi
    folder=$1
    if [ -e "$folder" ] && [ ! -d "$folder" ]; then
        fail "'$folder' already exists and is not a folder. Please pick another name."
    fi
    if [ -d "$folder" ] && [ -n "$(ls -A "$folder")" ]; then
        fail "The folder '$folder' already has files in it, so I did not touch it. Pick a new name."
    fi

    mkdir -p "$folder/.vscode"

    cat >"$folder/main.py" <<'EOF'
# Welcome! This is your first program.
# Save this file (Ctrl+S or Cmd+S) and look at your browser: it updates every time you save.

# The canvas is 800 wide and 600 tall. The point (0, 0) is in the middle.
Grid()

# A red circle in the middle. Change the color, or the radius, and save again.
ball = Circle(0, 0, radius=60, color="tomato")

print("Hello! I made a ball.")

# Wait one second, then slide the ball to the right.
wait(1)
ball.x = 150

# Your turn: try ball.y = 100, or make a Rectangle(-150, 0).
EOF

    cat >"$folder/pyrightconfig.json" <<'EOF'
{
  "stubPath": "typings",
  "reportUndefinedVariable": "error"
}
EOF

    cat >"$folder/.vscode/settings.json" <<'EOF'
{
  "python.analysis.typeCheckingMode": "basic",
  "python.analysis.stubPath": "typings"
}
EOF

    if [ -f "$ROOT/engine/typings/__builtins__.pyi" ]; then
        mkdir -p "$folder/typings"
        cp "$ROOT/engine/typings/__builtins__.pyi" "$folder/typings/__builtins__.pyi"
    else
        say "Warning: the editor help file (engine/typings/__builtins__.pyi) was not found," >&2
        say "so autocomplete in your editor will not work yet. Your program will still run." >&2
    fi

    say "Created a new project in '$folder'."
    say ""
    say "Next step: run it with"
    case $folder in
        *[!A-Za-z0-9._/+-]*) say "  $invoked \"$folder/main.py\"" ;;
        *) say "  $invoked $folder/main.py" ;;
    esac
}

case ${1-} in
    "" | -h | --help | help)
        usage
        exit 0
        ;;
    new)
        shift
        new_project "$@"
        exit 0
        ;;
esac

need_python

if [ ! -f "$ROOT/engine/lib/core/__main__.py" ]; then
    fail "The Python Playground engine (engine/lib/core) is missing from $ROOT."
fi

PYTHONPATH=$ROOT/engine/lib${PYTHONPATH:+:$PYTHONPATH}
export PYTHONPATH
PLAYGROUND_PROG=$invoked
export PLAYGROUND_PROG

# Python puts the current folder first on its search path. Take it off before importing anything,
# so a student's file called random.py, queue.py or core.py cannot get in the way.
BOOT='import os,sys,runpy;c=os.getcwd()
sys.path[:]=[p for p in sys.path if p and os.path.abspath(p)!=c]
runpy.run_module("core",run_name="__main__",alter_sys=True)'
exec "$PYTHON" -c "$BOOT" "$@"
