PYTHON ?= python

.PHONY: init-config install install-pg install-mariadb start ping migrate lint format

# cluster admin commands

init-config:
	cp --backup=numbered warden/lib/config/config.sample.yaml warden/lib/config/config.yaml

install:
	@test -f warden/lib/config/config.yaml || $(MAKE) init-config
	pip install -r requirements.txt

install-pg: install
	pip install -r requirements.txt -r requirements-pg.txt

install-mariadb: install
	pip install -r requirements.txt -r requirements-mariadb.txt

start: migrate
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
	${PYTHON} -m uvicorn warden.api.main:app --host 0.0.0.0 --port 4207 & PIDS+=($$!); \
	${PYTHON} -m warden.scheduler & PIDS+=($$!); \
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

# dev/contributors methods

.PHONY: install-dev start-dev start-mock-pasqos start-mock-pasqos-dev test lint-check lint-fix update-requirements run-db alembic

install-dev:
	@test -f warden/lib/config/config.yaml || $(MAKE) init-config
	python -m pip install poetry==2.3.3
	poetry install --with dev --all-extras
	$(MAKE) migrate

start-dev: migrate
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
	${PYTHON} -m debugpy --listen 0.0.0.0:8888 -m uvicorn warden.api.main:app --reload --host 0.0.0.0 --port 4207 & PIDS+=($$!); \
	${PYTHON} -m debugpy --listen 0.0.0.0:8889 -m warden.scheduler & PIDS+=($$!); \
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

# Usage: make alembic ARGS="upgrade head"
alembic:
	${PYTHON} -m alembic -c warden/api/alembic.ini $(ARGS)
