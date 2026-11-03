# Spec: tooling, scripts, stubs and docs

Owners: WP-T (Makefile, scripts, README, syllabus), WP-S (stubs, mkdocs, docs content).

## Already in place (do not rewrite)

`mise.toml` (uv + glci), `.python-version` (3.12, dev only), `pyproject.toml` (dependency groups
`dev`, `docs`, `e2e`; pytest, ruff, pyright config), `.gitignore`, `uv.lock`. Ask in your report
if you need changes to them.

## Makefile (WP-T; WP-CI adds CI targets)

All targets run through `uv run` (`mise exec -- uv ...` if `uv` is not on PATH: detect with
`command -v uv || ...`; define `UV := mise exec -- uv` when `uv` is missing but `mise` exists).
`make help` (default goal) lists targets with one-line descriptions (`## comment` pattern).

| Target | Does |
|---|---|
| `install` | `uv sync --all-groups` |
| `install-browsers` | `uv run playwright install chromium` |
| `run SCRIPT=examples/x/main.py` | `./run.sh $(SCRIPT)` |
| `test` | unit/host/browser-free tests: `pytest -m "not e2e"` |
| `test-min` | same, with `uv run --python 3.10` (isolated env) |
| `e2e` | `pytest -m e2e` |
| `lint` | `ruff check`, `ruff format --check`, `pyright` |
| `fmt` | `ruff format`, `ruff check --fix` |
| `stubs` | generate `engine/typings/__builtins__.pyi` |
| `stubs-check` | fail if the committed stub differs from generated |
| `docs` | build the mkdocs site into `site/` (`mkdocs build --strict`) |
| `docs-serve` | `mkdocs serve` |
| `check` | `lint`, `test`, `stubs-check`, `docs` |
| `clean` | remove `site/ public/ .pytest_cache .ruff_cache` and `__pycache__` |

## `run.sh` (WP-T)

POSIX `sh`, executable, works from any directory, resolves the repo root from `$0`.

```
./run.sh path/to/main.py [--port N] [--no-browser]   run a program
./run.sh new <folder>                                create a new student project
./run.sh --help
```

- Finds `python3` (>= 3.10; else friendly error pointing at `install.sh`), sets
  `PYTHONPATH=<root>/engine/lib`, runs `python3 -m core "$@"`. Never uses uv/mise/make.
- No arguments: prints usage plus the list of `examples/*/`.
- `new <folder>`: refuses to overwrite an existing non-empty folder. Creates `main.py` (a short
  friendly starter with a few lines: a `Circle`, a `print`), `pyrightconfig.json`
  (`{"stubPath": "typings", "reportUndefinedVariable": "error"}`-style minimal config), a
  `typings/__builtins__.pyi` **copied** from `engine/typings`, and a `.vscode/settings.json`
  (`python.analysis.typeCheckingMode: "basic"`, `python.analysis.stubPath: "typings"`).
  Prints the next step (`./run.sh <folder>/main.py`).

## `install.sh` (WP-T)

POSIX `sh`; **placeholder for students/teachers, not developers.** Checks, never installs:
python3 present and >= 3.10, a web browser can be opened (macOS `open`, Linux `xdg-open`,
else a hint), and (optional hint) VS Code + Python extension for editor autocomplete.
Prints one friendly line per check (`ok` / `missing: how to get it`), exits non-zero if
Python is missing/too old. TODO comment block at the end for future steps (venv, examples).

## `README.md` (WP-T)

Project overview for GitLab: what/why, 60-second quick start (`./run.sh examples/...`), student
workflow, link to the published docs (relative, mkdocs site), repository layout, developer
quick start (`mise install`, `make install`, `make check`), license placeholder. Keep to one
screen plus a layout table. No push-specific URLs (the GitLab project path is unknown):
use relative links.

## Syllabus placeholder (WP-T)

`syllabus/README.md`: "TBD" plus the initial topic list: variables, print, intro to graphic
objects, tour of graphic objects, control flow, loops, functions, lists, dictionaries, sets, OOP.

## Editor stub (WP-S)

`engine/tools/gen_stubs.py` (uses `griffe` to load `core`, pure function `generate() -> str`,
`python engine/tools/gen_stubs.py [--check]`). Writes `engine/typings/__builtins__.pyi`:

- Header comment: generated, do not edit, regenerate with `make stubs`.
- Contains every name in `core.__all__`: classes (with bases, `__init__` signature including
  the positional/keyword-only rules from `api.md`, property annotations, methods) and functions
  with their **docstrings**, so hover shows help in VS Code.
- Deterministic output (sorted/stable) so `--check` is meaningful.
- **Verified mechanism:** Pyright reads `<stubPath>/__builtins__.pyi` and adds its symbols to the
  builtins scope. Result: no `import` needed, autocomplete + hover + argument checking, and
  genuinely undefined names (typos) are still reported by `reportUndefinedVariable`.
  Add a test in `engine/tests/tools/` that runs `pyright` (from the dev env, `uv run pyright
  --outputjson`) on a temp project containing a sample `main.py` + the generated stub and asserts:
  API names resolve, a wrong argument type is flagged, `c.colour` is flagged, an undefined
  name is flagged.
- The root `pyrightconfig` equivalent lives in `pyproject.toml` (`stubPath = "engine/typings"`).
  Each example folder gets its own `pyrightconfig.json` (WP-X) pointing `stubPath` to the
  relative `../../engine/typings` so opening the folder alone also works.

## Docs (WP-S): mkdocs-material + mkdocstrings

- `mkdocs.yml` at the repo root: Material theme (light/dark toggle, instant navigation,
  search, code copy), `mkdocstrings` python handler (Google docstrings, source paths
  `engine/lib`, signature annotations, members ordered by source, show docstring attributes),
  `site_url: !ENV [SITE_URL, ""]` so GitLab Pages can inject `$CI_PAGES_URL`,
  `use_directory_urls: true`, `strict` friendly (no broken links/anchors).
- Pages (plain Markdown readable in an editor; `:::` directives are the only enhancement):
  - `docs/index.md`: welcome, what it is, 60-second start (kid- and teacher-friendly), links.
  - `docs/getting-started.md`: install check, run an example, `./run.sh new`, VS Code setup
    (stub config), what the browser page shows (status, console, errors), the program
    lifecycle, the event loop idea (`while True: wait(...)`).
  - `docs/engine/index.md` (API overview table), `shapes.md` (Circle, Rectangle, Triangle,
    Line, Text, Shape), `guides.md` (Grid, Axis), `functions.md` (canvas, wait, get),
    `events.md` (on_click, on_key + the event-loop explanation), `errors.md` (what friendly
    errors look like).
  - `docs/developer/` is owned by the coordinator (architecture, plan, specs): include it in
    the nav (`Developer` section) but do not edit those files.
- `nav` explicit in `mkdocs.yml`. The `docs` group in `pyproject.toml` provides dependencies.
- `make docs` builds with `--strict` and must pass with zero warnings.

## Package data

`core/static/` must be found via `Path(__file__).parent / "static"`. No installation step is
needed; `PYTHONPATH=engine/lib` is enough.
