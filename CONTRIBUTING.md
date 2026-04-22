# Contributing to Warden


## Dev requirements

On top of the requirements from [README.md](README.md), the following are required

- docker compose
- A Python interpreter (default: `python3`)

## Getting started

If you have a fresh environment, you may get started with:

```bash
make install-dev
```

This will:
- Create the local `venv` if missing
- Install Poetry in the selected Python environment
- Configure Poetry to use in-project virtualenvs (`.venv`)
- Install dependencies
- Create the default `config.yaml` file at the project root if it does not exist yet
- Run migrations for the default SQLite DB

## Shared Poetry setup targets

To keep local setup and CI setup aligned, Poetry bootstrap is centralized in `Makefile` targets:

- `make poetry-bootstrap`: install pinned Poetry and configure in-project virtualenvs
- `make poetry-install-dev`: install dev dependencies with all extras
- `make poetry-setup-dev`: convenience target combining the two commands above

`make install-dev` reuses these targets and then runs migrations.

When updating CI or onboarding docs, prefer reusing these targets rather than duplicating inline Poetry setup commands.

## Run dev server

> You will need a database instance accessible locally. For convenience a simple sqlite DB is provided as a default. This db was already initialized if you ran the `make install-dev` above. See below for more details about the DB.

```bash
make dev
```

Verify the API is running:

```bash
make ping
```

## Databases

### Run with another database

By default Warden runs on a local SQLite database.

Alternatively, Warden can be configured to connect to other SQL database like postgres/mariadb by tweaking environment variables. See [README.md](README.md) for more details about configuration.

A docker compose file is provided with the db setup for postgresql, run it:

```bash
make run-db
```

## Running Alembic migrations - notes on `ARGS` usage

The `alembic` Make target forwards the `ARGS` variable directly to the underlying `alembic` command. Some common examples:

- **Upgrade to latest migration**:

```bash
make alembic ARGS="upgrade head"
```

- **Downgrade one revision**:

```bash
make alembic ARGS="downgrade -1"
```

Anything you would normally put after `alembic` in the CLI should be passed via `ARGS`.

## Adding dependencies 

In the dev environment you may use poetry to manage your dependencies, but end users ultimately use `make` targets that rely on [`requirements.txt`](requirements.txt) so that they don't need to install `poetry` to run `warden`. That is why it is important to keep [`requirements.txt`](requirements.txt) updated.

### Updating requirements.txt

Using the [`poetry export`](https://github.com/python-poetry/poetry-plugin-export) plugin we can export the locked packages to the `requirements.txt` format:

```bash
make update-requirements
```
