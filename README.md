# Warden

Middleware for the integration of a QPU into an HPC center. It is composed of two main components:
- an API which receives jobs from users, validates and stores them in DB (external or SQLite)
- a worker which schedules the jobs and sends them for execution on a QPU


## Requirements

- Python 3.11 / 3.12
- make, git, curl, build toolchain
- [munge](https://github.com/dun/munge/wiki/Installation-Guide)

For optional/dev requirements, check [CONTRIBUTING.md](CONTRIBUTING.md)

## Installation

Quick install/update (one-liner) - follow the instructions:

```bash
curl -fsSL https://raw.githubusercontent.com/pasqal-io/warden/main/install.sh | bash
```

Notes:
- The installer currently checks out tag `WARDEN_VERSION=v0.1.0`, can be overridden
- Make sure you have the rights to create the target Warden folder `/opt/warden`
- Make sure you change your configuration at `/opt/warden/config.yaml`
- If you need to change the database type used (e.g. from SQLite to PSQL), you need to run the install process again to install the required dependencies

## Next steps

### Run Warden

```bash
cd /opt/warden && make run
```

### Deploy as systemd

Depending on your use-case and specific situation, you may want to run Warden in a different way.

One option is to use a systemd configuration like the one described in [docs/install/systemd](docs/install/systemd).

### Configuration

Configuration is done:
1. using the config file `config.yaml` at the project root
2. using environment variables - takes precedence over the config file

Configuration keys from `config.yaml` can be set or overridden by environment variables by converting the key path to uppercase, prefixing it with `WARDEN_`, and separating nested keys with underscores.

For example, given the following YAML:

```yaml
database:
  # It's best not to set secrets in a file on-disk
  # password: secret
```

Since it's best not to have secrets written on disk, we set it using an environment variable:

```bash
WARDEN_DATABASE_PASSWORD="secret"
```

The following options are configurable:

- API bind address and port
- QPU API uri
- Database backend
- Scheduler polling intervals
- Logging (see `config.yaml` for more configuration details)

### API server

The API server host and port are configurable through the YAML config or environment:

| Path       | Variable          | Description             | Default   | Required | Example Value |
|------------|-------------------|-------------------------|-----------|----------|---------------|
| `api.host` | `WARDEN_API_HOST` | API bind host address   | `0.0.0.0` | Yes      | `127.0.0.1`   |
| `api.port` | `WARDEN_API_PORT` | API bind port           | `8006`    | Yes      | `8080`        |

### QPU 

Warden's access to the PASQAL QPU can be configured through the YAML config or environment:

| Path       | Variable          | Description             | Default                 | Required | Example Value             |
|------------|-------------------|-------------------------|-------------------------|----------|---------------------------|
| `qpu.uri`  | `WARDEN_QPU_URI`  | PASQAL QPU API uri      | `http://localhost:8005` | Yes      | `http://127.0.0.1:8005`   |


The API server can also be configured to only accept new jobs from configured user IDs:

| Path       | Description             | Default   | Required | Example Value |
|------------|-------------------------|-----------|----------|---------------|
| `api.authorized_users` | List of user IDs auhorized to create new jobs  | `[]` | Yes      | `["1000", "2000", "0"]`   |

The default value `[]` allows all users to create new jobs.

### Database

Warden supports the following databases:
- Local SQLite (default)
- PostgreSQL
- MariaDB

Below is a table of all configuration variables available for Warden's database:

| Path                | Variable            | Description                                                     | Default       | Required                     | Example Value                    |
|---------------------|---------------------|-----------------------------------------------------------------|---------------|------------------------------|----------------------------------|
| `database.backend`  | `WARDEN_DATABASE_BACKEND`  | Backend type for the database. Supported: `sqlite`, `postgres`, `mariadb` | `sqlite`      | Yes                          | `postgres`                       |
| `database.name`     | `WARDEN_DATABASE_NAME`     | Name of the database (filename for sqlite, db name for postgres/mariadb) |               | Yes                          | `warden.db` <br> `warden`        |
| `database.host`     | `WARDEN_DATABASE_HOST`     | Host address of the database server (PostgreSQL/MariaDB)       | `localhost`   | No                           | `localhost`                      |
| `database.port`     | `WARDEN_DATABASE_PORT`     | Port for connecting to the database server (PostgreSQL/MariaDB) | `5432`/`3306` | No                           | `5432`                           |
| `database.user`     | `WARDEN_DATABASE_USER`     | Username for the database connection (PostgreSQL/MariaDB)      |               | If using Postgres/MariaDB    | `postgres`                       |
| `database.password` | `WARDEN_DATABASE_PASSWORD` | Password for the database user (PostgreSQL/MariaDB)            |               | If using Postgres/MariaDB    | `secretpassword`                 |

**Note:**
- **IT IS RECOMMENDED NOT TO SAVE PASSWORDS IN CLEARTEXT FILES SUCH AS `config.yaml`!**
- Only `WARDEN_DATABASE_BACKEND` and `WARDEN_DATABASE_NAME` are required for SQLite (default), which are set in the default config file.
- For PostgreSQL, you must provide at least `WARDEN_DATABASE_USER` and `WARDEN_DATABASE_PASSWORD`, and often `WARDEN_DATABASE_HOST` and `WARDEN_DATABASE_PORT` depending on your environment.
- All variables can be set in the `config.yaml` file (but passwords _should_ not) _or_ as an environment variable.

Example for PostgreSQL:

```yaml
# config.yaml
database:
  backend: postgres
  name: warden
  host: localhost
  port: 5432
  user: postgres
```

Secrets are defined as environment variables:

```bash
WARDEN_DATABASE_PASSWORD=secretpassword
```

### Configure accessibility

You can configure Warden to reject all incoming jobs by running the following target as root user:

```bash
make set-accessible IS_ACCESSIBLE=false MESSAGE="Scheduled QPU maintenance"
```

Configure Warden to accept jobs again by configuring:

```bash
make set-accessible IS_ACCESSIBLE=true MESSAGE="Maintenance done"
```
