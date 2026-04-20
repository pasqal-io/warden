include config.mk


.PHONY: alembic dev install install-dev lint-check lint-fix migrate ping run \
 run-db run-with-python set-accessible start-mock-qpu start-mock-qpu-dev \
 test update-requirements

INSTALL_FLAGS=
ifeq ($(WITH_PG),1)
INSTALL_FLAGS  += -r requirements-pg.txt
endif
ifeq ($(WITH_MARIADB),1)
INSTALL_FLAGS  += -r requirements-mariadb.txt
endif
REQUIREMENTS_EXPORT_DIR ?= .

# cluster admin commands

config.yaml:
	@new_config="warden/lib/config/config.sample.yaml"; \
	if [ ! -f config.yaml ]; then \
		cp "$$new_config" config.yaml; \
		exit 0; \
	fi; \
	if cmp -s "$$new_config" config.yaml; then \
		exit 0; \
	fi; \
	last_i=0; \
	i=1; \
	while [ -e "config.backup-$$i.yaml" ]; do \
		last_i=$$i; \
		i=$$((i + 1)); \
	done; \
	if [ "$$last_i" -eq 0 ] || ! cmp -s config.yaml "config.backup-$$last_i.yaml"; then \
		cp config.yaml "config.backup-$$i.yaml"; \
	fi; \
	cp "$$new_config" config.yaml

# Note: the --copies flag is used to create a copy of the binaries, since a symlink may not always work
$(VENV)/bin/python: config.yaml
	@if [ -z "$(PYTHON)" ]; then \
		echo "Usage: make venv PYTHON=/path/to/python"; \
		exit 1; \
	fi
	@if [ -d $(VENV) ]; then \
		echo "$(VENV) already created"; \
	else \
		echo "Creating $(VENV) with $(PYTHON)"; \
		$(PYTHON) -m venv --copies $(VENV); \
		echo "Virtualenv created in $(VENV) using $(PYTHON)"; \
	fi

install: $(VENV)/bin/python
	$(VENV)/bin/python -m pip install -r requirements.txt $(INSTALL_FLAGS)

run: migrate
	@bash -c '\
	set -uo pipefail; \
	PIDS=(); \
	cleanup() { \
		trap - SIGINT SIGTERM EXIT; \
		if [ "$${#PIDS[@]}" -gt 0 ]; then \
			kill -TERM "$${PIDS[@]}" 2>/dev/null || true; \
			for pid in "$${PIDS[@]}"; do \
				wait "$$pid" 2>/dev/null || true; \
			done; \
		fi; \
	}; \
	on_signal() { \
		cleanup; \
		exit 0; \
	}; \
	trap on_signal SIGINT SIGTERM; \
	trap cleanup EXIT; \
	$(VENV)/bin/python -m warden.api.main & PIDS+=($$!); \
	$(VENV)/bin/python -m warden.scheduler & PIDS+=($$!); \
	set +e; \
	wait -n "$${PIDS[@]}"; \
	STATUS=$$?; \
	set -e; \
	cleanup; \
	exit $$STATUS'



migrate:
	$(MAKE) alembic ARGS="upgrade head"

# cluster admin warden requests 
URL ?= http://localhost:8006
MESSAGE ?= Update

define ACCESSIBLE_POST_JSON_PAYLOAD
{"is_accessible": $(IS_ACCESSIBLE), "message": "$(MESSAGE)"}
endef

set-accessible:

	@if [ -z "$(IS_ACCESSIBLE)" ]; then \
		echo "ERROR 'IS_ACCESSIBLE' is required."; \
		echo "Usage: make set-accessible IS_ACCESSIBLE=[true|false] MESSAGE=\"Update\""; \
		exit 1; \
	fi

	curl -X POST $(URL)/accessible \
		-H "X-Munge-Cred: $$(munge -n)" \
		-H "Content-Type: application/json" \
		-d '$(ACCESSIBLE_POST_JSON_PAYLOAD)'

ping:
	curl $(URL)

run-with-python:
	$(VENV)/bin/python -m warden

alembic:
	$(VENV)/bin/python -m alembic -c warden/api/alembic.ini $(ARGS)

# dev/contributors methods

install-dev: config.yaml
	$(VENV)/bin/python -m pip install poetry==2.3.3
	$(VENV)/bin/python -m poetry install --with dev --all-extras
	$(MAKE) migrate

dev: migrate
	@bash -c '\
	set -uo pipefail; \
	PIDS=(); \
	cleanup() { \
		trap - SIGINT SIGTERM EXIT; \
		if [ "$${#PIDS[@]}" -gt 0 ]; then \
			kill -TERM "$${PIDS[@]}" 2>/dev/null || true; \
			for pid in "$${PIDS[@]}"; do \
				wait "$$pid" 2>/dev/null || true; \
			done; \
		fi; \
	}; \
	on_signal() { \
		cleanup; \
		exit 0; \
	}; \
	trap on_signal SIGINT SIGTERM; \
	trap cleanup EXIT; \
	$(VENV)/bin/python -m debugpy --listen 0.0.0.0:8888 -m warden.api.main --reload & PIDS+=($$!); \
	$(VENV)/bin/python -m debugpy --listen 0.0.0.0:8889 -m warden.scheduler & PIDS+=($$!); \
	set +e; \
	wait -n "$${PIDS[@]}"; \
	STATUS=$$?; \
	set -e; \
	cleanup; \
	exit $$STATUS'

start-mock-qpu: $(VENV)/bin/python
	$(VENV)/bin/python -m uvicorn mock_qpu_api.app:app --app-dir tests

start-mock-qpu-dev: $(VENV)/bin/python
	$(VENV)/bin/python -m uvicorn mock_qpu_api.app:app --reload --app-dir tests

test:
	poetry run pytest

lint-check:
	poetry run ruff check .
	poetry run ruff format --check .

lint-fix:
	poetry run ruff check --fix .
	poetry run ruff format .

update-requirements:
	mkdir -p "$(REQUIREMENTS_EXPORT_DIR)"
	poetry export -f requirements.txt --output "$(REQUIREMENTS_EXPORT_DIR)/requirements.txt"
	poetry export -f requirements.txt --extras postgres --output "$(REQUIREMENTS_EXPORT_DIR)/requirements-pg.txt"
	poetry export -f requirements.txt --extras mariadb --output "$(REQUIREMENTS_EXPORT_DIR)/requirements-mariadb.txt"

run-db:
	docker compose up -d
