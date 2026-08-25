VENV ?= .venv
PYTHON ?= $(VENV)/bin/python
BOOTSTRAP_PYTHON ?= python3
FORMAT ?= text
REPORT_FORMAT ?= xlsx
VENV_STAMP := $(VENV)/.yettel-dev-installed

.PHONY: help install install-dev refresh-venv yettel run status login phones usage all-usage report test lint format check precommit-install precommit-run precommit-uninstall clean

help:
	@echo "Yettel flotta CLI"
	@echo ""
	@echo "Targets:"
	@echo "  make install                    Install the CLI in editable mode"
	@echo "  make install-dev                Create/refresh .venv with local test/lint tools"
	@echo "  make refresh-venv               Delete and rebuild .venv"
	@echo "  make yettel                     Run lint/tests, then start the menu"
	@echo "  make run                        Start the numbered interactive menu"
	@echo "  make status                     Show local session status"
	@echo "  make login                      Log in using .env credentials"
	@echo "  make phones                     List phone numbers from the portal"
	@echo "  make usage PHONE=205...         Fetch usage for a phone number"
	@echo "  make all-usage                  Fetch all phone numbers and save an export"
	@echo "  make report                     Build full business report"
	@echo "  make test                       Run unit tests"
	@echo "  make lint                       Run ruff lint"
	@echo "  make format                     Run ruff format"
	@echo "  make check                      Run lint and tests"
	@echo "  make precommit-install          Install git pre-commit hook"
	@echo "  make precommit-run              Run pre-commit hooks on all files"
	@echo "  make precommit-uninstall        Remove git pre-commit hook"
	@echo "  make clean                      Remove local Python caches"
	@echo ""
	@echo "Options:"
	@echo "  FORMAT=text|json|csv|xlsx       Output format for usage/all-usage"
	@echo "  REPORT_FORMAT=xlsx|csv|json|text Output format for report"
	@echo "  VENV=.venv                      Local virtual environment path"

$(PYTHON):
	$(BOOTSTRAP_PYTHON) -m venv $(VENV)

install: $(PYTHON)
	$(PYTHON) -m pip install -e .

$(VENV_STAMP): pyproject.toml $(PYTHON)
	$(PYTHON) -m pip install -e ".[dev]"
	@touch $(VENV_STAMP)

install-dev: $(VENV_STAMP)

refresh-venv:
	@if [ -d "$(VENV)" ]; then \
		find "$(VENV)" -name .DS_Store -delete; \
		rm -rf "$(VENV)"; \
	fi
	$(MAKE) install-dev

yettel: check run

run: $(VENV_STAMP)
	PYTHONPATH=src $(PYTHON) -m yettel_cli

status: $(VENV_STAMP)
	PYTHONPATH=src $(PYTHON) -m yettel_cli status

login: $(VENV_STAMP)
	PYTHONPATH=src $(PYTHON) -m yettel_cli login

phones: $(VENV_STAMP)
	PYTHONPATH=src $(PYTHON) -m yettel_cli phones

usage: $(VENV_STAMP)
	@if [ -z "$(PHONE)" ]; then \
		echo "Usage: make usage PHONE=201234567 [FORMAT=text|json|csv|xlsx]"; \
		exit 2; \
	fi
	PYTHONPATH=src $(PYTHON) -m yettel_cli usage "$(PHONE)" --format "$(FORMAT)"

all-usage: $(VENV_STAMP)
	PYTHONPATH=src $(PYTHON) -m yettel_cli all-usage --format "$(FORMAT)" --save

report: $(VENV_STAMP)
	PYTHONPATH=src $(PYTHON) -m yettel_cli report --format "$(REPORT_FORMAT)"

test: install-dev
	PYTHONPATH=src $(PYTHON) -m pytest

lint: install-dev
	PYTHONPATH=src $(PYTHON) -m ruff check .

format: install-dev
	PYTHONPATH=src $(PYTHON) -m ruff format .

check: lint test

precommit-install: install-dev
	PYTHONPATH=src $(PYTHON) -m pre_commit install

precommit-run: install-dev
	PYTHONPATH=src $(PYTHON) -m pre_commit run --all-files

precommit-uninstall: install-dev
	PYTHONPATH=src $(PYTHON) -m pre_commit uninstall

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type d -name .pytest_cache -prune -exec rm -rf {} +
	find . -type d -name .ruff_cache -prune -exec rm -rf {} +
	find . -type d -name "*.egg-info" -prune -exec rm -rf {} +
