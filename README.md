# Warden

Middleware for the integration of a QPU into an HPC center. It is composed of two main components:
- an API which receives jobs from users, validates and stores them in DB (external or SQLite)
- a worker which schedules the jobs and sends them for execution on a QPU


## Requirements

- make
- [munge](https://github.com/dun/munge/wiki/Installation-Guide)

For optional/dev requirements, check [CONTRIBUTING.md](CONTRIBUTING.md)

## Installation

Quick install/update (one-liner):

```bash
# curl -fsSL https://raw.githubusercontent.com/pasqal-io/warden/main/install.sh | sudo bash
curl -fsSL https://raw.githubusercontent.com/pasqal-io/warden/ac9173bb463cf70198f8611eebbbfff1b4a83e40/install.sh | sudo bash
```

## More details

Create the default config file `warden/lib/config/config.yaml` (creates a backup of your existing config if it exists):

The config file is created automatically by `make install` if it does not exist.

Install Warden dependencies:

```bash
make install
```

If you plan to use PostgreSQL or MariaDB as a backend, install those dependencies as well:

```bash
# Add PostgreSQL dependencies
make install-pg
# Or MariaDB
make install-mariadb
```

## Run Warden

```bash
make run
```

## Configuration

Configuration is done:
1. using the config file `warden/lib/config/config.yaml`
2. using environment variables - takes precedence over the config file

Configuration keys from `warden/lib/config/config.yaml` can be set or overridden by environment variables, by converting the key path to uppercase and separating nested keys with underscores.

For example, given the following YAML:

```yaml
database:
  # It's best not to set secrets in a file on-disk
  # password: secret
```

Since it's best not to have secrets written on disk, we set it using an environment variable:

```bash
DATABASE_PASSWORD="secret"
```

The following options are configurable:

- Database backend
- API bind address and port
- Logging (see `warden/lib/config/config.yaml` for more configuration details)

### API server

The API server host and port are configurable through the YAML config or environment:

| Path/Variable        | Description                                                               | Default           | Required | Example Value                                    |
|----------------------|---------------------------------------------------------------------------|-------------------|----------|--------------------------------------------------|
| `api.host` (config file) <br> `API_HOST` (env var) | API bind host address                                                   | `0.0.0.0`         | No       | `127.0.0.1`                                      |
| `api.port` (config file) <br> `API_PORT` (env var) | API bind port                                                           | `4207`            | No       | `8080`                                           |

### Database

Warden supports the following databases:
- Local SQLite (default)
- PostgreSQL
- MariaDB

Below is a table of all configuration variables available for Warden's database:

| Path/Variable        | Description                                                               | Default           | Required | Example Value                                    |
|----------------------|---------------------------------------------------------------------------|-------------------|----------|--------------------------------------------------|
| `database.backend` (config file) <br> `DATABASE_BACKEND` (env var) | Backend type for the database. Supported: `sqlite`, `postgres`, `mariadb`          | `sqlite`          | Yes   | `postgres`                                     |
| `database.name` (config file) <br> `DATABASE_NAME` (env var) | Name of the database (filename for sqlite, db name for postgres/mariadb)          |         | Yes      | `warden.db` <br> `warden`         |
| `database.host` (config file) <br> `DATABASE_HOST` (env var) | Host address of the database server (PostgreSQL/MariaDB)                     | `localhost`       | No       | `localhost`              |
| `database.port` (config file) <br> `DATABASE_PORT` (env var) | Port for connecting to the database server (PostgreSQL/MariaDB)   | `5432`/`3306`  | No       | `5432`                  |
| `database.user` (config file) <br> `DATABASE_USER` (env var) | Username for the database connection (PostgreSQL/MariaDB)                    |                   | If using Postgres/MariaDB | `postgres`                                  |
| `DATABASE_PASSWORD` (env var) | Password for the database user (PostgreSQL/MariaDB)                          |                   | If using Postgres/MariaDB | `secretpassword`                            |

**Note:**
- **IT IS RECOMMENDED NOT TO SAVE PASSWORDS IN CLEARTEXT FILES SUCH AS `warden/lib/config/config.yaml`!**
- Only `DATABASE_BACKEND` and `DATABASE_NAME` are required for SQLite (default), which are set in the default config file.
- For PostgreSQL, you must provide at least `DATABASE_USER` and `DATABASE_PASSWORD`, and often `DATABASE_HOST` and `DATABASE_PORT` depending on your environment.
- All variables can be set in the `warden/lib/config/config.yaml` file (but passwords _should_ not) _or_ as an environment variable.

Example for PostgreSQL:

```yaml
# warden/lib/config/config.yaml
database:
  backend: postgres
  name: warden
  host: localhost
  port: 5432
  user: postgres
```

Secrets are defined as environment variables:

```bash
DATABASE_PASSWORD=secretpassword
```
