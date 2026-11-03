# Developer tooling. Students never need this file: they use run.sh.
# Run `make` or `make help` to list the targets.

# uv on PATH, else through mise (see mise.toml).
ifneq ($(shell command -v uv 2>/dev/null),)
UV := uv
else ifneq ($(shell command -v mise 2>/dev/null),)
UV := mise exec -- uv
else
UV := uv
endif

RUN := $(UV) run
SCRIPT ?= examples/solar-system/main.py

.DEFAULT_GOAL := help

.PHONY: help install install-browsers run test test-min e2e lint fmt stubs stubs-check \
	docs docs-serve check clean _need-uv

help: ## Show this list of targets
	@echo "Python Playground developer targets:"
	@echo
	@grep -E '^[a-zA-Z0-9_-]+:.*## ' $(MAKEFILE_LIST) | sort | \
		awk -F ':.*## ' '{ printf "  %-18s %s\n", $$1, $$2 }'
	@echo
	@echo "Example: make run SCRIPT=examples/catch-the-stars/main.py"

_need-uv:
	@command -v uv >/dev/null 2>&1 || command -v mise >/dev/null 2>&1 || { \
		echo "Neither 'uv' nor 'mise' was found. Install mise (https://mise.jdx.dev) and run 'mise install'."; \
		exit 1; }

install: _need-uv ## Install every dependency group (uv sync --all-groups)
	$(UV) sync --all-groups

install-browsers: _need-uv ## Install Chromium for the browser tests
	$(RUN) playwright install chromium

run: ## Run a program: make run SCRIPT=examples/x/main.py
	@test -f "$(SCRIPT)" || { echo "Cannot find '$(SCRIPT)'. Try: make run SCRIPT=examples/<name>/main.py"; exit 1; }
	./run.sh "$(SCRIPT)"

test: _need-uv ## Run the fast tests (everything except e2e)
	$(RUN) pytest -m "not e2e"

test-min: _need-uv ## Same as test, on Python 3.10 in an isolated environment
	$(RUN) --python 3.10 --isolated --group dev pytest -m "not e2e" --ignore=engine/tests/e2e --ignore=engine/tests/browser

e2e: _need-uv ## Run the browser tests (needs: make install-browsers)
	$(RUN) pytest -m e2e

lint: _need-uv ## ruff check, ruff format --check, pyright
	$(RUN) ruff check engine
	$(RUN) ruff format --check engine
	$(RUN) pyright

fmt: _need-uv ## Format and auto-fix the code
	$(RUN) ruff format engine
	$(RUN) ruff check --fix engine

stubs: _need-uv ## Generate engine/typings/__builtins__.pyi (editor autocomplete)
	@test -f engine/tools/gen_stubs.py || { echo "engine/tools/gen_stubs.py does not exist yet (stub generator not written)."; exit 1; }
	$(RUN) python engine/tools/gen_stubs.py

stubs-check: _need-uv ## Fail if the committed stub is out of date
	@test -f engine/tools/gen_stubs.py || { echo "engine/tools/gen_stubs.py does not exist yet (stub generator not written)."; exit 1; }
	$(RUN) python engine/tools/gen_stubs.py --check

docs: _need-uv ## Build the documentation site into site/ (strict)
	@test -f mkdocs.yml || { echo "mkdocs.yml does not exist yet (docs not written)."; exit 1; }
	NO_MKDOCS_2_WARNING=1 $(RUN) mkdocs build --strict

docs-serve: _need-uv ## Preview the documentation site while editing
	@test -f mkdocs.yml || { echo "mkdocs.yml does not exist yet (docs not written)."; exit 1; }
	$(RUN) mkdocs serve

check: lint test stubs-check docs ## Everything CI checks: lint, test, stubs-check, docs

clean: ## Remove build output, caches and __pycache__ folders
	rm -rf site public .pytest_cache .ruff_cache test-results .uv-cache
	find . -name .venv -prune -o -name .git -prune -o -type d -name __pycache__ -exec rm -rf {} +

# CI helpers (used by .gitlab-ci.yml; also handy to reproduce a CI job locally).
PYTHON ?= 3.12
SITE_DIR ?= site

.PHONY: ci-test ci-e2e ci-docs

ci-test: _need-uv ## CI: fast tests on one Python (make ci-test PYTHON=3.10), JUnit in test-results/
	$(RUN) --python $(PYTHON) --isolated --group dev pytest -m "not e2e" --ignore=engine/tests/e2e --ignore=engine/tests/browser --junitxml=test-results/junit-$(PYTHON).xml

ci-e2e: _need-uv ## CI: browser tests with the Chromium that is already installed (Playwright image)
	$(UV) sync --group dev --group e2e
	$(RUN) --no-sync pytest -m e2e --junitxml=test-results/junit-e2e.xml

ci-docs: _need-uv ## CI: strict docs build into SITE_DIR (make ci-docs SITE_DIR=public)
	NO_MKDOCS_2_WARNING=1 $(RUN) --group docs mkdocs build --strict --site-dir $(SITE_DIR)
