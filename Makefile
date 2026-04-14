PYTHON ?= python

.PHONY: init-config install install-pg install-mariadb start ping migrate lint format set-accessible

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
	python -m uvicorn warden.api.main:app --host 0.0.0.0 --port 4207

start-scheduler:
	python  -m warden.scheduler

migrate:
	$(MAKE) alembic ARGS="upgrade head"

# cluster admin warden requests 

URL ?= http://localhost:4207
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

# dev/contributors methods

.PHONY: install-dev start-dev start-mock-pasqos start-mock-pasqos-dev test lint-check lint-fix update-requirements run-db alembic

install-dev:
	@test -f warden/lib/config/config.yaml || $(MAKE) init-config
	python -m pip install poetry==2.3.3
	poetry install --with dev --all-extras
	$(MAKE) migrate

start-dev: migrate
	poetry run python -m debugpy --listen 0.0.0.0:8888 -m uvicorn warden.api.main:app --reload --host 0.0.0.0 --port 4207

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
	python -m alembic -c warden/api/alembic.ini $(ARGS)
