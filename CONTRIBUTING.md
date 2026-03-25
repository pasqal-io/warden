# Contributing to Warden


## Dev requirements

On top of the requirements from [README.md](README.md), the following are required

- docker compose
- [poetry](https://python-poetry.org/docs/#installation)

## Getting started

If you have a fresh environment, you may get started with:

```bash
make install-dev
```

This will:
- Install Poetry
- Install dependencies
- Create the default `warden/lib/config/config.yaml` file if it does not exist yet
- Run migrations for the default SQLite DB

## Run dev server

```bash
make install
```

## Run in development mode

> You will need a database instance accessible locally. For convenience a simple sqlite DB is provided as a default. This db was already initialized if you ran the `make install-dev` above. See below for more details about the DB.

Run the API with hot-reload:

```bash
make start-dev
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
