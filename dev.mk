include config.mk

.PHONY: install-dev dev
.PHONY: start-mock-qpu-dev 
.PHONY: start-qutip-qpu-dev
.PHONY: migrate alembic revision
.PHONY: lint-check lint-fix type-check
.PHONY: run-with-python
.PHONY: test test-sqlite test-postgres test-mariadb
.PHONY: test-migrations test-migrations-sqlite test-migrations-postgres test-migrations-mariadb
.PHONY: update-requirements run-db

VENV=.venv
REQUIREMENTS_EXPORT_DIR ?= .
POETRY_VERSION ?= 2.4.1
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
PG_TEST_DB ?= warden_test
PG_MIGRATIONS_TEST_DB ?= warden_migrations_test

MARIADB_TEST_PORT ?= 3306
MARIADB_TEST_USER ?= root
MARIADB_TEST_PASSWORD ?= secret
MARIADB_TEST_ADMIN_USER ?= $(MARIADB_TEST_USER)
MARIADB_TEST_ADMIN_PASSWORD ?= $(MARIADB_TEST_PASSWORD)
MARIADB_TEST_ADMIN_DB ?= warden
MARIADB_TEST_DB ?= warden_test
MARIADB_MIGRATIONS_TEST_DB ?= warden_migrations_test

SQLITE_MIGRATIONS_TEST_DB ?= /tmp/warden_test.db


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

start-mock-qpu-dev: $(VENV)/bin/python
	$(VENV)/bin/python -m uvicorn mock_qpu_api.app:app --reload --app-dir tests

start-qutip-qpu-dev: $(VENV)/bin/python
	MOCK_QPU_API_EMUL=true $(MAKE) start-mock-qpu-dev

alembic:
	$(VENV)/bin/python -m alembic -c warden/api/alembic.ini $(ARGS)

test: test-sqlite test-postgres test-mariadb

test-sqlite: test-migrations-sqlite
	WARDEN_TEST_DATABASE_BACKEND=sqlite $(POETRY_PYTHON) -m poetry run pytest -k "$(EXPR)"

test-postgres: test-migrations-postgres
	WARDEN_TEST_DATABASE_BACKEND=postgres \
	$(POETRY_PYTHON) -m poetry run pytest -k "$(EXPR)"

test-mariadb: test-migrations-mariadb
	WARDEN_TEST_DATABASE_BACKEND=mariadb \
	$(POETRY_PYTHON) -m poetry run pytest -k "$(EXPR)"

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
	mysql --protocol=TCP -h $(MARIADB_TEST_HOST) -P $(MARIADB_TEST_PORT) -u $(MARIADB_TEST_ADMIN_USER) --password=$(MARIADB_TEST_ADMIN_PASSWORD) $(MARIADB_TEST_ADMIN_DB) -e "DROP DATABASE IF EXISTS \`$(MARIADB_MIGRATIONS_TEST_DB)\`; CREATE DATABASE \`$(MARIADB_MIGRATIONS_TEST_DB)\`;"
	WARDEN_DATABASE_BACKEND=mariadb \
	WARDEN_DATABASE_HOST=$(MARIADB_TEST_HOST) \
	WARDEN_DATABASE_PORT=$(MARIADB_TEST_PORT) \
	WARDEN_DATABASE_USER=$(MARIADB_TEST_ADMIN_USER) \
	WARDEN_DATABASE_NAME=$(MARIADB_MIGRATIONS_TEST_DB) \
	WARDEN_DATABASE_PASSWORD=$(MARIADB_TEST_ADMIN_PASSWORD) \
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

type-check:
	$(POETRY_PYTHON) -m poetry run pyright

update-requirements:
	$(POETRY_PYTHON) -m poetry lock
	mkdir -p "$(REQUIREMENTS_EXPORT_DIR)"
	$(POETRY_PYTHON) -m poetry export -f requirements.txt --output "$(REQUIREMENTS_EXPORT_DIR)/requirements.txt"
	$(POETRY_PYTHON) -m poetry export -f requirements.txt --extras postgres --output "$(REQUIREMENTS_EXPORT_DIR)/requirements-pg.txt"
	$(POETRY_PYTHON) -m poetry export -f requirements.txt --extras mariadb --output "$(REQUIREMENTS_EXPORT_DIR)/requirements-mariadb.txt"

run-db:
	docker compose up -d

# Usage: make revision MESSAGE="Update database schema"
revision:
	$(MAKE) alembic ARGS="revision --autogenerate -m \"$(MESSAGE)\""
