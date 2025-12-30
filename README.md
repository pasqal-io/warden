# Warden

Middleware for the integration of a QPU into an HPC center. It is composed of two main components:
- an API which receives jobs from users, validates and stores them in DB
- a worker which schedules the jobs and sends them for execution on a QPU


## Requirements

- poetry
- [just](https://github.com/casey/just)
- [munge](https://github.com/dun/munge/wiki/Installation-Guide)
- docker compose


## Installation

```bash
just install
```

## Run in development mode

You will need a sql db instance accessible locally. For convenience a simple sqlite DB is provided as a default.

Run the migrations to setup the db:
```bash
just alembic upgrade head
```

Then run the API:

```bash
just start
```

Verify the API is running:

```bash
just ping
```

Alternatively, Warden can be configured to connect to other SQL database like postgres by tweaking environment variables.
**TODO: Document how to tweak the .env file.**
A docker compose file is provided with the db setup, run it:

```bash
just run-db
```