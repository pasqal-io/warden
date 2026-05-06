include config.mk


.PHONY: alembic dev install install-dev lint-check lint-fix migrate ping \
 run run-db run-with-python set-accessible \
 start-mock-qpu start-mock-qpu-dev test test-migrations test-migrations-mariadb \
 test-migrations-postgres test-migrations-sqlite update-requirements

VENV=.venv
INSTALL_FLAGS=
ifeq ($(WITH_PG),1)
INSTALL_FLAGS  += -r requirements-pg.txt
endif
ifeq ($(WITH_MARIADB),1)
INSTALL_FLAGS  += -r requirements-mariadb.txt
endif
REQUIREMENTS_EXPORT_DIR ?= .
POETRY_VERSION ?= 2.3.3
POETRY_PYTHON ?= $(VENV)/bin/python
POETRY_EXTRA_PACKAGES ?=

IN_DEVCONTAINER := $(shell if [ -f /.dockerenv ]; then echo 1; else echo 0; fi)
ifeq ($(IN_DEVCONTAINER),1)
PG_TEST_HOST ?= warden-db-postgres
MARIADB_TEST_HOST ?= warden-db-mariadb
else
PG_TEST_HOST ?= localhost
MARIADB_TEST_HOST ?= localhost
endif

PG_TEST_PORT ?= 5432
PG_TEST_USER ?= wardenuser
PG_TEST_PASSWORD ?= secret
PG_TEST_ADMIN_USER ?= $(PG_TEST_USER)
PG_TEST_ADMIN_PASSWORD ?= $(PG_TEST_PASSWORD)
PG_TEST_ADMIN_DB ?= postgres
PG_MIGRATIONS_TEST_DB ?= warden_migrations_test

MARIADB_TEST_PORT ?= 3306
MARIADB_TEST_USER ?= root
MARIADB_TEST_PASSWORD ?= secret
MARIADB_TEST_ADMIN_USER ?= $(MARIADB_TEST_USER)
MARIADB_TEST_ADMIN_PASSWORD ?= $(MARIADB_TEST_PASSWORD)
MARIADB_TEST_ADMIN_DB ?= warden
MARIADB_MIGRATIONS_TEST_DB ?= warden_migrations_test

SQLITE_MIGRATIONS_TEST_DB ?= /tmp/warden_migrations_test.db

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
	@if [ -d ./venv ]; then \
		echo "Removing legacy ./venv"; \
		rm -rf ./venv; \
	fi
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
install-dev: $(VENV)/bin/python install
	$(POETRY_PYTHON) -m pip install poetry==$(POETRY_VERSION) $(POETRY_EXTRA_PACKAGES)
	$(POETRY_PYTHON) -m poetry env use $(VENV)/bin/python
	$(POETRY_PYTHON) -m poetry install --with dev --all-extras

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
	$(POETRY_PYTHON) -m poetry run pytest

test-migrations: test-migrations-sqlite test-migrations-mariadb test-migrations-postgres

test-migrations-postgres:
	# Run against an isolated PostgreSQL database.
	PGPASSWORD=$(PG_TEST_ADMIN_PASSWORD) psql -h $(PG_TEST_HOST) -p $(PG_TEST_PORT) -U $(PG_TEST_ADMIN_USER) -d $(PG_TEST_ADMIN_DB) -c "DROP DATABASE IF EXISTS $(PG_MIGRATIONS_TEST_DB);"
	PGPASSWORD=$(PG_TEST_ADMIN_PASSWORD) psql -h $(PG_TEST_HOST) -p $(PG_TEST_PORT) -U $(PG_TEST_ADMIN_USER) -d $(PG_TEST_ADMIN_DB) -c "CREATE DATABASE $(PG_MIGRATIONS_TEST_DB);"
	WARDEN_DATABASE_BACKEND=postgres \
	WARDEN_DATABASE_HOST=$(PG_TEST_HOST) \
	WARDEN_DATABASE_PORT=$(PG_TEST_PORT) \
	WARDEN_DATABASE_USER=$(PG_TEST_USER) \
	WARDEN_DATABASE_NAME=$(PG_MIGRATIONS_TEST_DB) \
	WARDEN_DATABASE_PASSWORD=$(PG_TEST_PASSWORD) \
	$(MAKE) migrate

test-migrations-mariadb:
	# Run against an isolated MariaDB database.
	mysql --protocol=TCP -h $(MARIADB_TEST_HOST) -P $(MARIADB_TEST_PORT) -u $(MARIADB_TEST_ADMIN_USER) -p$(MARIADB_TEST_ADMIN_PASSWORD) $(MARIADB_TEST_ADMIN_DB) -e "DROP DATABASE IF EXISTS \`$(MARIADB_MIGRATIONS_TEST_DB)\`; CREATE DATABASE \`$(MARIADB_MIGRATIONS_TEST_DB)\`;"
	WARDEN_DATABASE_BACKEND=mariadb \
	WARDEN_DATABASE_HOST=$(MARIADB_TEST_HOST) \
	WARDEN_DATABASE_PORT=$(MARIADB_TEST_PORT) \
	WARDEN_DATABASE_USER=$(MARIADB_TEST_USER) \
	WARDEN_DATABASE_NAME=$(MARIADB_MIGRATIONS_TEST_DB) \
	WARDEN_DATABASE_PASSWORD=$(MARIADB_TEST_PASSWORD) \
	$(MAKE) migrate

test-migrations-sqlite:
	# Run against an isolated SQLite database file.
	rm -f "$(SQLITE_MIGRATIONS_TEST_DB)"
	WARDEN_DATABASE_BACKEND=sqlite \
	WARDEN_DATABASE_NAME=$(SQLITE_MIGRATIONS_TEST_DB) \
	$(MAKE) migrate

lint-check:
	$(POETRY_PYTHON) -m poetry run ruff check .
	$(POETRY_PYTHON) -m poetry run ruff format --check .

lint-fix:
	$(POETRY_PYTHON) -m poetry run ruff check --fix .
	$(POETRY_PYTHON) -m poetry run ruff format .

update-requirements:
	$(POETRY_PYTHON) -m poetry lock
	mkdir -p "$(REQUIREMENTS_EXPORT_DIR)"
	$(POETRY_PYTHON) -m poetry export -f requirements.txt --output "$(REQUIREMENTS_EXPORT_DIR)/requirements.txt"
	$(POETRY_PYTHON) -m poetry export -f requirements.txt --extras postgres --output "$(REQUIREMENTS_EXPORT_DIR)/requirements-pg.txt"
	$(POETRY_PYTHON) -m poetry export -f requirements.txt --extras mariadb --output "$(REQUIREMENTS_EXPORT_DIR)/requirements-mariadb.txt"

run-db:
	docker compose up -d
