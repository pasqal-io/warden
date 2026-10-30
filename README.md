# Warden

Middleware for the integration of a QPU into an HPC center. It is composed of two main components:
- an API which receives jobs from users, validates and stores them in DB (external or SQLite)
- a worker which schedules the jobs and sends them for execution on a QPU


## Requirements

- Python 3.11 / 3.12 / 3.13 / 3.14
- make, git, curl, build toolchain
- [munge](https://github.com/dun/munge/wiki/Installation-Guide)

For optional/dev requirements, check [CONTRIBUTING.md](CONTRIBUTING.md)

Release process documentation lives in [RELEASING.md](RELEASING.md).

## Installation

Quick install/update (one-liner) - follow the instructions:

```bash
curl -fsSL https://raw.githubusercontent.com/pasqal-io/warden/main/install.sh | bash
```

Notes:
- The installer currently checks out tag `WARDEN_VERSION=0.3.2`, can be overridden
- Make sure you have the rights to create the target Warden folder `/opt/warden`
- Make sure to check the generated `/opt/warden/config.yaml` configuration file
- If you need to change the database type used (e.g. from SQLite to PSQL), you need to run the install process again to install the required dependencies

## Operating

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

> [!NOTE]
> If a key contains an underscore, you need to remove any `_` in its name to set it using environment variables.
> E.g. `qpu.retry_max` can be set with the `WARDEN_QPU_RETRYMAX` environment variable.


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

| Path             | Variable                | Description                          | Default                 | Required | Example Value             |
|------------------|-------------------------|--------------------------------------|-------------------------|----------|---------------------------|
| `qpu.uri`        | `WARDEN_QPU_URI`        | PASQAL QPU API uri                   | `http://localhost:8005` | Yes      | `http://127.0.0.1:8005`   |
| `qpu.tls_verify` | `WARDEN_QPU_TLSVERIFY`   | TLS verification for an https backend | `system`                | No       | `system`                  |

`qpu.tls_verify` only applies when `qpu.uri` uses `https`. It accepts:

- `system`: verify against the OS trust store (default). Use this for backends with self-signed certs: add the CA to `/etc/pki/ca-trust/source/anchors/` and run `update-ca-trust` (or `/etc/ssl/certs`).
- `true`: verify against the bundled (certifi) CA store.
- `false`: disable verification entirely. **Insecure**, dev/local testing only.
- a path (e.g. `/etc/warden/backend-ca.pem`) — verify against a specific CA bundle / certificate file.


The API server can also be configured to only accept new jobs from configured user IDs:

| Path       | Description             | Default   | Required | Example Value |
|------------|-------------------------|-----------|----------|---------------|
| `api.authorized_users` | List of user IDs auhorized to create new jobs  | `[]` | Yes      | `["1000", "2000", "0"]`   |
| `api.admin_users` | List of admin user IDs authorized to administer QPU availability and create sessions on behalf of users | `[0]` | Yes | `[0, "1001"]` |
| `api.munge_audience` | Base URLs clients use to reach Warden; MUNGE credentials must be issued for one of them | `[]` | No | `["http://warden:4207"]` |

The default value `[]` for `api.authorized_users` allows all users to create new jobs.

`api.admin_users` must not be empty. The uid running the spank plugin must be
included in `api.admin_users`; otherwise the plugin cannot acquire a session and
Warden is unusable with it.

See [Binding MUNGE credentials to Warden](#binding-munge-credentials-to-warden-apimunge_audience)
for `api.munge_audience`.

### Binding MUNGE credentials to Warden (`api.munge_audience`)

A MUNGE credential proves the client's uid but not which server it was meant
for. A server that receives one, for instance through a wrong Warden URL in a
client's configuration, could relay it to Warden once within its lifetime and
act as that uid, an admin uid included. To prevent this, clients sign the
request into the credential's payload, and Warden checks it when
`api.munge_audience` is set.

**Payload format.** `<METHOD> <URL>`, separated by one space:

- `<METHOD>`: the HTTP method in upper case, e.g. `GET`, `POST`, `DELETE`.
- `<URL>`: the base URL the client uses for Warden, exactly as configured on the
  client (scheme, host and port, plus a path prefix if Warden is behind a
  proxy), followed by the request path, e.g. `http://warden:4207/sessions`.
  The query string is not part of it.

QRMI (from qiskit-community/qrmi#334) signs every request this way. By hand:

```bash
curl -H "X-Munge-Cred: $(munge -s 'GET http://warden:4207/status')" http://warden:4207/status
```

**Configuration.** `api.munge_audience` lists every base URL clients use, e.g.
`["http://warden:4207", "http://localhost:8006"]` (the second for the admin
commands of the Makefile, run on the Warden host). A trailing `/` in an entry
is ignored. Warden accepts a credential when its method is the request's and
its URL is one of the entries followed by the request path. When the list is
empty (the default), the payload is not checked.

**Troubleshooting.** A refused credential gets
`401 MUNGE credential not issued for this request to this Warden`, and Warden
logs a warning with what was signed and what it accepts:

```
Refused a MUNGE credential signed for 'GET http://10.0.0.5:4207/status' on GET /status; accepted: '<METHOD> <base URL><path>' with base URLs ['http://warden:4207']
```

| Signed payload | Cause | Fix |
|---|---|---|
| `''` (empty) | The client does not sign requests: QRMI older than #334, or `munge -n` by hand | Update QRMI; use `munge -s` |
| Another host name, IP address or port | The client reaches Warden under a URL not in the list | Add that base URL to `api.munge_audience`, or use the listed one on the client |
| `http` instead of `https` (or the reverse), or a missing path prefix | The client's URL differs from the listed one | Make them identical |
| A host you do not know | A credential relayed from another server | Nothing to fix: the check did its job |

### Accounting API

Warden exposes usage-reporting endpoints under `/accounting`, restricted to
`api.admin_users`:

| Route                      | Description                              |
|----------------------------|------------------------------------------|
| `GET /accounting`          | Per-user summary of sessions and jobs    |
| `GET /accounting/sessions` | Per-session detail                       |
| `GET /accounting/jobs`     | Per-job detail                           |

All three accept `start_datetime` (required), `end_datetime`, `user_ids` and
pagination (`limit`, `offset`) as query parameters, and filter on session
`revoked_at`. `GET /accounting/sessions` additionally accepts `slurm_job_id` filtering,
and `GET /accounting/jobs` accepts `session_id` and `status` filtering.

See FastAPI's `/docs` page for the full request/response schema of each
route.

### Status API

`GET /status` returns a live snapshot of Warden's current activity, restricted
to `api.admin_users`: 
- the number of pending jobs
- the job currently running
- and the list of open sessions.
Historical jobs/sessions are not included, see the Accounting API above for reporting.

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

## Work with a containerized cluster

If Warden runs in a container next to a containerized HPC cluster (Slurm, LSF, Open Cluster Scheduler, ...), the
container where Warden runs must be reachable from the cluster's network. List the networks of any cluster node, for
example the controller or head node:

```bash
docker inspect <cluster-node> --format '{{range $k, $v := .NetworkSettings.Networks}}{{$k}}{{"\n"}}{{end}}'
```

Connect the Warden container to that network and check it from a cluster node:

```bash
docker network connect <network> <warden-container>
docker exec <cluster-node> curl -s http://<warden-container>:<port>/accessible
```

The cluster nodes then reach Warden by its container name, e.g. `QRMI_WARDEN_URL=http://<warden-container>:<port>`.
The nodes and Warden containers must have munge installed and share the same MUNGE key.

This works for any containerized cluster, for example the Slurm cluster of the
[QRMI SPANK plugin demo](https://github.com/qiskit-community/spank-plugins/blob/main/demo/qrmi/slurm-docker-cluster/INSTALL.md)
or [QFw-SLURM-Cluster](https://github.com/openQSE/QFw-SLURM-Cluster). The
[SC26 tutorial](https://github.com/qrmi-community/SC26) instead starts Warden with a simulated QPU on the cluster's own
network for Slurm, OpenPBS, LSF and Open Cluster Scheduler, e.g.
[`containers/slurm/compose.warden.yml`](https://github.com/qrmi-community/SC26/blob/main/containers/slurm/compose.warden.yml).
