# Plan

Delivery is split into work packages (WP) executed by parallel agents, coordinated from one
session. The coordinator commits after each wave in small conventional-commit chunks.
Nothing is ever pushed.

## Work packages

| WP | Scope | Spec |
|---|---|---|
| WP-A objects | Student-facing API, scene ops, child runtime, `wait`, events | `specs/api.md`, `specs/protocol.md` (runtime seam) |
| WP-B host | CLI, supervisor, watcher, SSE, runner, error payloads | `specs/protocol.md` |
| WP-C browser | The page: SVG renderer, console, status, errors, input | `specs/browser.md` |
| WP-T tooling | `Makefile`, `run.sh`, `install.sh`, README, syllabus | `specs/tooling.md` |
| WP-S stubs + docs | Stub generator, mkdocs site, API reference | `specs/tooling.md` |
| WP-I integration | End-to-end wiring, Playwright e2e, cross-module fixes | all |
| WP-X examples | Solar system, Catch the stars | `specs/examples.md` |
| WP-CI | `.gitlab-ci.yml`, Pages, `glci` runs | `specs/ci.md` |

## Waves

| Wave | Runs in parallel | Gate |
|---|---|---|
| 0 | Coordinator: tooling base, AGENTS.md, specs | committed |
| 1 | WP-A, WP-B, WP-C, WP-T | each package's tests green, lint clean |
| 2 | WP-I (wire A+B+C, e2e), WP-S (stubs + docs) | e2e green in Chromium, stub test green, `make docs` strict |
| 3 | WP-X (two examples) | examples verified in a real browser |
| 4 | WP-CI | `glci run` green for the pipeline |
| 5 | Review and polish | `make check` + e2e green |

## Definition of done (project)

- `make check` and `make e2e` pass.
- Both examples run in a real browser as specified (screenshots reviewed).
- `.gitlab-ci.yml` passes locally through `glci`.
- Docs build with `--strict`; stubs are up to date.
- All work committed locally in conventional-commit chunks. Nothing pushed.
