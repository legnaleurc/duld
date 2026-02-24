RM := rm -rf
PYTHON := uv run -- python3
RUFF := uv run -- ruff

PKG_FILES := pyproject.toml
PKG_LOCK := uv.lock
ENV_DIR := .venv
ENV_LOCK := $(ENV_DIR)/pyvenv.cfg

.PHONY: all format lint purge test

all: venv

format: venv
	$(RUFF) check --fix
	$(RUFF) format

lint: venv
	$(RUFF) check
	$(RUFF) format --check

purge:
	$(RM) $(ENV_DIR)

test: venv
	$(PYTHON) -m compileall duld

venv: $(ENV_LOCK)

$(ENV_LOCK): $(PKG_LOCK)
	uv sync
	touch $@

$(PKG_LOCK): $(PKG_FILES)
	uv lock
	touch $@
