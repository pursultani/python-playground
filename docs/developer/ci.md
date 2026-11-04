# CI and GitLab Pages

The pipeline lives in `.gitlab-ci.yml`. It runs for merge requests, the default branch and
manual web runs (no duplicate pipelines).

| Stage | Job | What it does |
|---|---|---|
| `lint` | `lint` | `make lint` (ruff, ruff format, pyright) and `make stubs-check` |
| `test` | `test` (Python 3.10, 3.11, 3.12, 3.13) | `make ci-test PYTHON=x.y`, isolated environments, JUnit report |
| `e2e` | `e2e` | `make ci-e2e` in the official Playwright image (tag must match the `playwright` version in `uv.lock`); screenshots and JUnit kept for a week, even on failure |
| `docs` | `docs` | `make ci-docs`: strict mkdocs build into `site/` |
| `pages` | `pages` | Default branch only. Builds with `SITE_URL=$CI_PAGES_URL` into `public/` and publishes with `pages: true` |

Conventions: pinned uv image, `UV_FROZEN=1` (CI never edits the lockfile), the uv cache in
`.uv-cache/` keyed on `uv.lock`, jobs are `interruptible`.

## Reproduce locally

- A single job's work: run its make target, for example `make ci-test PYTHON=3.10`.
- The real job in Docker (needs Docker or colima running):

```sh
mise exec -- glci lint                                             # validate the YAML
mise exec -- glci run "test: [3.10]" --secrets none --no-token     # one matrix leg
mise exec -- glci run pages --context branch=main --secrets none --no-token
```

`glci` copies uncommitted files, so a run includes work in progress. `.glciconfig.toml` skips
GitLab's implicit `.pre` stage so local runs work. Nothing in the setup contacts GitLab.

## GitHub Pages

The docs are also published from GitHub by `.github/workflows/pages.yml`. On every push to
`main` it runs the same `make ci-docs SITE_DIR=public` with
`SITE_URL=https://pursultani.github.io/python-playground/`, then deploys with the official
Pages actions. It only publishes docs; the lint and test jobs stay on GitLab.

One-time setup: in the GitHub repository, set **Settings → Pages → Source** to **GitHub Actions**.
If you move the repository or add a custom domain, update `SITE_URL` in the workflow.

## Maintenance

- Bump the Playwright image tag whenever `playwright` changes in `uv.lock`.
- `UV_VERSION` in the CI file and the `version` in the GitHub workflow track `mise.toml`.
- The image has no `make`; jobs install it with `apt-get`.
