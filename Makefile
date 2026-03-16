PYTHON ?= python

.PHONY: init-config install install-pg install-mariadb start ping migrate

# cluster admin commands

init-config:
	cp --backup=numbered warden/config/config.sample.yaml warden/config/config.yaml

install:
	@test -f warden/config/config.yaml || $(MAKE) init-config
	pip install -r requirements.txt

install-pg: install
	pip install -r requirements.txt -r requirements-pg.txt

install-mariadb: install
	pip install -r requirements.txt -r requirements-mariadb.txt

start: migrate
	python -m uvicorn warden.main:app --host 0.0.0.0 --port 4207

ping:
	curl localhost:4207

migrate:
	$(MAKE) alembic ARGS="upgrade head"

# dev/contributors methods

.PHONY: install-dev test run-db alembic requirements requirements-pg requirements-mariadb requirements-all

install-dev:
	@test -f warden/config/config.yaml || $(MAKE) init-config
	python -m pip install poetry==1.8.4
	poetry install --with dev --all-extras
	$(MAKE) migrate

start-dev: migrate
	poetry run python -m debugpy --listen 0.0.0.0:8888 -m uvicorn warden.main:app --reload --host 0.0.0.0 --port 4207

requirements:
	poetry export -f requirements.txt --output requirements.txt

requirements-pg:
	poetry export -f requirements.txt --extras postgres --output requirements-pg.txt

requirements-mariadb:
	poetry export -f requirements.txt --extras mariadb --output requirements-mariadb.txt

requirements-all: requirements requirements-pg requirements-mariadb

test:
	poetry run pytest

run-db:
	docker compose up -d

# Usage: make alembic ARGS="upgrade head"
alembic:
	python -m alembic -c warden/alembic.ini $(ARGS)
