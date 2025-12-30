install:
  poetry install --with dev

start:
  poetry run uvicorn warden.main:app --reload --host 0.0.0.0 --port 4207

ping:
  curl localhost:4207

test:
  poetry run pytest

run-db:
  docker compose up -d

alembic *args:
  poetry run alembic -c warden/alembic.ini {{args}}
