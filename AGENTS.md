# AGENTS.md

Instructions for every AI agent (and human) working in this repository.
Read this file fully, then the specs in `docs/developer/specs/` that apply to your task.

## What this project is

**Python Playground**: a tiny framework for teaching children to program. A student writes plain
Python in any text editor, runs one command, and sees 2D graphics, `print` output and friendly
errors live in a browser tab. The Python package that makes this work is called **`core`**
(import root: `engine/lib`). Students never write `import`: the whole API is pre-loaded.

Priorities, in order: **(1) simplicity for the child, (2) look and feel of the graphics,
(3) correctness, (4) simplicity of the engine code.** When in doubt, pick the simpler behavior and
the clearer error message.

Read first: `docs/developer/architecture.md`, `docs/developer/plan.md`.
Specs (the source of truth for behavior):

| Spec | Covers |
|---|---|
| `docs/developer/specs/api.md` | Public Python API students use |
| `docs/developer/specs/protocol.md` | Processes, lifecycle, wire messages, CLI, error payloads |
| `docs/developer/specs/browser.md` | The page: rendering, console, status, errors |
| `docs/developer/specs/tooling.md` | Repo tooling, stubs, docs generation, scripts |
| `docs/developer/specs/ci.md` | GitLab CI and Pages |
| `docs/developer/specs/examples.md` | The example programs |

If a spec is ambiguous or wrong, **do not silently diverge**: make the smallest reasonable
choice, and record it in your final report under "Spec questions / deviations".

## Repository layout

```
engine/lib/core/      the package (stdlib only at runtime, Python >= 3.10)
  static/             browser page (index.html, app.js, style.css)
engine/tests/         unit/ host/ browser/ e2e/ tools/  (one folder per owner, see below)
engine/tools/         dev scripts: gen_stubs.py, gen_docs helpers
engine/typings/       GENERATED editor stub (__builtins__.pyi), committed
docs/                 mkdocs site (index.md, developer/, engine/)
examples/<name>/      runnable programs: main.py (+ pyrightconfig.json)
syllabus/             TBD, placeholder only
run.sh  install.sh    student-facing scripts (plain POSIX sh + system python3)
Makefile mise.toml pyproject.toml uv.lock   developer tooling
```

## Hard rules

1. **Do NOT run `git push`, and do not add remotes or contact GitLab.** The coordinator
   commits. **Do not run `git commit`, `git add`, `git reset`, `git stash`, or `git checkout`
   yourself** (several agents work in the same checkout at once). Leave your work as
   uncommitted files in your owned paths.
2. **Only edit files you own** (listed in your task). Need a change elsewhere? Report it in
   "Spec questions / deviations" and, if it is a one-line blocker, make it and say so.
3. **Runtime dependencies: none.** `engine/lib/core` imports only the Python standard library
   and must work on Python 3.10, 3.11, 3.12, 3.13+. Dev/docs/e2e tooling lives in
   `pyproject.toml` dependency groups.
4. Students only need `python3` (>= 3.10) and a browser. `run.sh` and `install.sh` must never
   require `uv`, `mise`, or `make`.
5. Never use CDNs or the network at runtime. The browser page is self-contained: no build step,
   no frameworks, vanilla JS/CSS/HTML.
6. Never kill processes you did not start. Run servers on random free ports in tests, never a
   fixed port, and always clean them up (use fixtures / `try/finally`).
7. Temporary files go under `/private/var/folders/mm/y6zzp5q160n30k0hz12tgp7m0000gn/T/opencode`,
   not the repo and not `/tmp`.

## Commands

Use the `make` targets (they wrap `uv`, which is provided by `mise`). From the repo root:

```
mise exec -- uv sync --all-groups       # install everything (already done)
mise exec -- uv run pytest engine/tests/<your folder>     # your tests
mise exec -- uv run ruff check engine && mise exec -- uv run ruff format engine
mise exec -- uv run pyright
mise exec -- uv run pytest -m e2e engine/tests/e2e         # browser tests (Chromium installed)
```

(Once `Makefile` exists: `make test`, `make lint`, `make e2e`, `make docs`, `make stubs`,
`make check`. If `mise exec --` is awkward in your shell, `mise` shims or `.venv/bin/*` also work.)

## Code style

- Python: ruff (line length 100), type hints on public functions, `from __future__ import annotations`
  where useful for 3.10 compatibility. No third-party imports in `engine/lib/core`.
- **Comments:** match the surrounding density; default to none. Comment only non-obvious *why*.
  **Docstrings are different**: every public name (class, function, method, property) needs a
  docstring, because the API docs and editor hover text are generated from them. Write them for a
  10-year-old's teacher: plain words, one short sentence first, then an `Example:` block that
  actually runs. Use Google-style sections (`Args:`, `Example:`).
- Error messages shown to students are plain English, no jargon, and say how to fix the problem.
  Offer "Did you mean ...?" for typos (`difflib.get_close_matches`).
- JS: modern ES2020, no dependencies, `"use strict"`, small functions, no minification.
- CSS: one file, CSS variables for the palette, no preprocessors.
- Keep files focused. Prefer a few deep modules over many shallow ones.

## Testing

- Tests must be deterministic and fast (unit tests < 1 s each). No fixed sleeps longer than
  necessary; poll with timeouts instead.
- **Definition of done for a feature:** unit/protocol tests pass **and**, for anything visible,
  it has been exercised in a real browser (Playwright, `-m e2e`), and you looked at a screenshot
  when appearance matters (save to the temp dir, never into the repo).
- A task is not finished until `ruff check`, `ruff format --check`, `pyright` and your tests are
  green for the files you own.

## Report format

End your work with a short report:

1. What you built (files).
2. How you verified it (commands + results).
3. Spec questions / deviations.
4. Known gaps / follow-ups.

## Ownership map (by work package, see `docs/developer/plan.md`)

| WP | Owner scope |
|---|---|
| WP-A objects | `engine/lib/core/{__init__,_runtime,_scene,_props,_colors,shapes,guides,api}.py`, `engine/tests/unit/` |
| WP-B host | `engine/lib/core/{__main__,supervisor,runner,_protocol,_errors}.py`, `engine/tests/host/` |
| WP-C browser | `engine/lib/core/static/`, `engine/tests/browser/` |
| WP-T tooling | `Makefile`, `run.sh`, `install.sh`, `README.md`, `syllabus/`, `engine/tests/tools/` (scripts only) |
| WP-S stubs+docs | `engine/tools/`, `engine/typings/`, `mkdocs.yml`, `docs/` (except `docs/developer/`) |
| WP-I integration | `engine/tests/e2e/` plus fixes anywhere in `engine/` (must be reported) |
| WP-X examples | `examples/` |
| WP-CI | `.gitlab-ci.yml` and CI-related Makefile targets |
