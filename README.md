# Python Playground

A tiny framework for teaching children to program. Write plain Python in any text editor, run one
command, and watch 2D graphics, `print` output and friendly errors update live in your browser.
There is nothing to install except Python 3.10+ and a browser, and you never write `import`.

## Quick start (60 seconds)

```sh
./install.sh                                 # checks that Python 3.10+ is ready
./run.sh examples/solar-system/main.py       # opens a browser tab with the program
```

## Student workflow

1. `./run.sh new my-program` creates a folder with a starter `main.py`.
2. `./run.sh my-program/main.py` starts the playground and opens your browser.
3. Edit `main.py` in any editor and save. The page restarts your program by itself.
4. Press Ctrl+C in the terminal to stop.

Using VS Code with the Python extension gives autocomplete and hints for free. See
[docs/index.md](docs/index.md) for the full guide (the documentation site is built with MkDocs).

## For developers

```sh
mise install          # installs uv (see mise.toml)
make install          # sync all dependency groups
make check            # lint, tests, stub check, docs build
make help             # every target
```

Browser tests need `make install-browsers` once, then `make e2e`. Start with
[docs/developer/architecture.md](docs/developer/architecture.md) and
[AGENTS.md](AGENTS.md).

## Repository layout

| Path | What is in it |
|---|---|
| [`engine/lib/core/`](engine/lib/core) | The `core` Python package (standard library only) and the browser page |
| [`engine/tests/`](engine/tests) | Unit, host, browser, e2e and tooling tests |
| [`engine/tools/`](engine/tools) | Developer scripts (editor stub generator) |
| [`engine/typings/`](engine/typings) | Generated `__builtins__.pyi` for editor autocomplete |
| [`examples/`](examples) | Runnable example programs |
| [`docs/`](docs) | Documentation site sources ([developer docs](docs/developer)) |
| [`syllabus/`](syllabus) | Course material (to be planned) |
| [`run.sh`](run.sh), [`install.sh`](install.sh) | Student scripts (plain `sh` and `python3`) |
| [`Makefile`](Makefile), [`mise.toml`](mise.toml), [`pyproject.toml`](pyproject.toml) | Developer tooling |

## License

To be decided.
