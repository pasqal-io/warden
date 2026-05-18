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
- Create the local `.venv` if missing
- Install Poetry in the selected Python environment
- Configure Poetry to use in-project virtualenvs (`.venv`)
- Install dependencies
- Create the default `config.yaml` file at the project root if it does not exist yet
- Run migrations for the default SQLite DB

## Shared Poetry setup targets

To keep local setup and CI setup aligned, Poetry bootstrap in CI is using the same `Makefile` target and uses `make install-dev`.

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

By default Warden runs on a local SQLite database.

Alternatively, Warden can be configured to connect to other SQL database like postgres/mariadb by tweaking environment variables. See [README.md](README.md) for more details about configuration.

The devcontainer setup includes containerized postgres an mariadb databases.

The same containers can be manually started from outside a devcontainer using:

```bash
make run-db
```

## Tests

### Integration and Unit tests

Run the full test suite using:

```bash
make test
```

To run subsets of the test suite:

```bash
# Unit/integration tests
make test-sqlite    # All tests, except psql/mariadb
make test-postgres  # All tests, except sqlite/mariad
make test-mariadb   # All tests, except postgres
# The formulation "all tests except xx and yy" is intentional, since it also includes all non-db-dependent tests

# Run subset of pytest test suite (equivent of `-k`) using EXPR, e.g.:
make test EXPR="sqlite and timeout"
# Expands (conceptually) to:
$(MAKE) test-migrations && $(PYTHON) -m pytest -k 'sqlite and timeout'

# Test migrations
make test-migrations # All
make test-migrations-sqlite
make test-migrations-postgres
make test-migrations-mariadb
```

Note: If you run `pytest` directly (either through the IDE or CLI), make sure you run the migrations first so the test db exists.

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

To add a dependency, first add it, then export all dependencies:

```bash
poetry add dependency
make update-requirements
```


### Updating requirements.txt

Using the [`poetry export`](https://github.com/python-poetry/poetry-plugin-export) plugin we can export the locked packages to the `requirements.txt` format:

```bash
make update-requirements
```
