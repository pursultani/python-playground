# Spec: GitLab CI and Pages

Owner: WP-CI. Use the **gitlab-ci-skill** (load it with the `skill` tool before authoring) and
validate everything locally with **`glci`** (provided by `mise.toml`; the Docker/colima runtime
is already running). **Never push**, never add a remote, never touch GitLab.com.

## Goals

- `.gitlab-ci.yml` at the repo root, readable, DRY (hidden `.base` jobs, `extends`), fast
  (uv cache keyed on `uv.lock`), using pinned image tags.
- Pipeline passes locally via `glci run` (for the jobs that can run in Docker locally).
- Publish the mkdocs site on **GitLab Pages**.

## Stages and jobs

| Stage | Job | Notes |
|---|---|---|
| `lint` | `lint` | `make lint` (ruff check, ruff format --check, pyright) and `make stubs-check` |
| `test` | `test` (matrix: Python 3.10, 3.11, 3.12, 3.13) | `uv run --python $PYTHON_VERSION pytest -m "not e2e"`; JUnit report artifact (`pytest --junitxml`) |
| `e2e` | `e2e` | Official Playwright Python image (pin a tag matching the `playwright` version in `uv.lock`); `make e2e`; screenshots/traces as artifacts `when: always`, expire 1 week |
| `docs` | `docs` | `make docs` -> `site/` artifact (also runs on merge requests so broken docs fail early) |
| `pages` | `pages` | Job named exactly `pages`; only on the default branch; `mkdocs build -d public` with `SITE_URL=$CI_PAGES_URL`; `artifacts: paths: [public]`; `pages: true` keyword if supported by the skill's guidance |

- `workflow:rules`: run on merge requests and the default branch; avoid duplicate pipelines.
- Base image for Python jobs: `ghcr.io/astral-sh/uv:python3.12-bookworm-slim` (or a pinned
  equivalent); install nothing with pip.
- `UV_CACHE_DIR` under `$CI_PROJECT_DIR/.uv-cache`; `cache:` keyed on `uv.lock`.
- `interruptible: true` on test/lint jobs.
- No secrets, no deploy tokens; Pages needs none.
- Add a short `docs/developer/ci.md` page? **No**, the coordinator owns `docs/developer/`;
  instead put a short "CI" section at the end of your final report; the coordinator will fold it
  in. The Makefile owner (WP-T) owns generic targets; you may add `ci-*` helper targets only.

## Local verification

1. `glci` lint/validate the file (see the skill and `glci --help` for the exact subcommands).
2. `glci run` each job possible locally (`lint`, `test`, `docs`, `pages`; `e2e` if the Playwright
   image can run under colima, else document why not and run the e2e target via `make e2e`
   directly). Capture the final status of every job in your report.
3. Fix real failures in CI config. If a failure is a product bug (test fails, docs warning),
   report it with details instead of editing source you do not own.
