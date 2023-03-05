RM := rm -rf
PYTHON := poetry run -- python3
BLACK := poetry run -- black

PKG_FILES := pyproject.toml
PKG_LOCK := poetry.lock
ENV_DIR := .venv
ENV_LOCK := $(ENV_DIR)/pyvenv.cfg

.PHONY: all format lint purge test venv

all: venv

format: venv
	$(BLACK) duld

lint: venv
	$(BLACK) --check duld

purge:
	$(RM) -rf $(ENV_DIR)

test: venv
	$(PYTHON) -m compileall duld

venv: $(ENV_LOCK)

$(ENV_LOCK): $(PKG_LOCK)
	poetry install
	touch $@

$(PKG_LOCK): $(PKG_FILES)
	poetry lock
	touch $@
