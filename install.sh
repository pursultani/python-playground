#!/bin/sh
# Python Playground setup check. Plain POSIX sh.
#
# This only LOOKS at your computer and tells you what is ready and what is missing.
# It never installs anything and never changes any file.
#
# Exit code: 0 when Python 3.10+ is available, 1 when it is missing or too old.

set -u

say() {
    printf '%s\n' "$*"
}

os=$(uname -s 2>/dev/null || echo unknown)

python_ok=0
python_cmd=
for candidate in python3 python3.15 python3.14 python3.13 python3.12 python3.11 python3.10; do
    command -v "$candidate" >/dev/null 2>&1 || continue
    if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' \
        >/dev/null 2>&1; then
        python_cmd=$candidate
        python_ok=1
        break
    fi
done

say "Python Playground setup check"
say ""

# 1. Python
if [ "$python_ok" -eq 1 ]; then
    version=$("$python_cmd" -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])' 2>/dev/null)
    say "ok: Python $version ($python_cmd)"
else
    old=
    if command -v python3 >/dev/null 2>&1; then
        old=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null) || old=
    fi
    if [ -n "$old" ]; then
        say "missing: Python 3.10 or newer (found python3 $old, which is too old)."
    else
        say "missing: Python 3.10 or newer (python3 was not found)."
    fi
    case $os in
        Darwin) say "         How to get it: download it from https://www.python.org/downloads/" ;;
        Linux) say "         How to get it: install it with your package manager, for example 'sudo apt install python3'." ;;
        *) say "         How to get it: download it from https://www.python.org/downloads/" ;;
    esac
fi

# 2. A web browser that can be opened from the terminal
if [ "$os" = "Darwin" ] && command -v open >/dev/null 2>&1; then
    say "ok: can open a web browser (open)"
elif command -v xdg-open >/dev/null 2>&1; then
    say "ok: can open a web browser (xdg-open)"
else
    say "missing: no way to open a browser automatically. That is fine:"
    say "         when the program starts, open the address it prints in any browser."
fi

# 3. Optional: VS Code for autocomplete
if command -v code >/dev/null 2>&1 || [ -d "/Applications/Visual Studio Code.app" ]; then
    say "ok: VS Code found (optional). Install its 'Python' extension for autocomplete."
else
    say "optional: VS Code gives you autocomplete and hints while you type."
    say "          Get it at https://code.visualstudio.com and add the 'Python' extension."
fi

say ""
if [ "$python_ok" -eq 1 ]; then
    say "You are ready. Try: ./run.sh --help"
    exit 0
fi
say "Please get Python 3.10 or newer, then run ./install.sh again."
exit 1

# TODO (future steps; the teaching material is still being planned):
#   - offer to create a virtual environment
#   - copy or open the example programs
#   - check that port 8765 is free
