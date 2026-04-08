include config.mk

.PHONY: install install-pg install-mariadb start ping alembic migrate lint format

INSTALL_FLAGS=
ifeq ($(WITH_PG),1)
INSTALL_FLAGS  += -r requirements-pg.txt
endif
ifeq ($(WITH_MARIADB),1)
INSTALL_FLAGS  += -r requirements-mariadb.txt
endif

# cluster admin commands

$(INSTALL_DIR)warden/lib/config/config.yaml:
	cp --backup=numbered warden/lib/config/config.sample.yaml warden/lib/config/config.yaml

$(VENV)/bin/python: $(INSTALL_DIR)warden/lib/config/config.yaml
	@if [ -z "$(PYTHON)" ]; then \
		echo "Usage: make venv PYTHON=/path/to/python"; \
		exit 1; \
	fi
	@if [ -d $(VENV) ]; then \
		echo "$(VENV) already created"; \
	else \
		echo "Creating $(VENV) with $(PYTHON)"; \
		$(PYTHON) -m venv $(VENV); \
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

ping:
	curl localhost:4207

migrate:
	$(MAKE) alembic ARGS="upgrade head"

alembic:
	$(VENV)/bin/python -m alembic -c warden/api/alembic.ini $(ARGS)

# dev/contributors methods

.PHONY: install-dev start-dev start-mock-pasqos start-mock-pasqos-dev test lint-check lint-fix update-requirements run-db alembic

install-dev:
	@test -f warden/lib/config/config.yaml || $(MAKE) init-config
	$(VENV)/bin/python -m pip install poetry==2.3.3
	poetry install --with dev --all-extras
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

start-mock-pasqos:
	cd tests && uvicorn mock_pasqos_api.app:app

start-mock-pasqos-dev:
	cd tests && uvicorn mock_pasqos_api.app:app --reload

test:
	poetry run pytest

lint-check:
	poetry run ruff check .
	poetry run ruff format --check .

lint-fix:
	poetry run ruff check --fix .
	poetry run ruff format .

update-requirements:
	poetry export -f requirements.txt --output requirements.txt
	poetry export -f requirements.txt --extras postgres --output requirements-pg.txt
	poetry export -f requirements.txt --extras mariadb --output requirements-mariadb.txt

run-db:
	docker compose up -d
