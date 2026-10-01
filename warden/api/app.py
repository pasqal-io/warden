import importlib.metadata
import logging
import tomllib
from pathlib import Path

from fastapi import FastAPI

from warden.api.routes import accessible, acct, jobs, qpu, sessions, status
from warden.api.routes.dependencies.auth import init_auth
from warden.api.routes.dependencies.db import init_db
from warden.api.routes.dependencies.qpu_client import init_qpu_client
from warden.lib.config import Config

PYPROJECT = Path(__file__).parents[2] / "pyproject.toml"

TAGS_METADATA = [
    {
        "name": "accounting",
        "description": "Accounting endpoints for Warden usage report generation.",
    }
]


def create_app(config: Config):
    app = FastAPI(
        title="Warden API",
        description="Receives, validates, and stores jobs for execution",
        version="0.2.0",
        openapi_tags=TAGS_METADATA,
    )
    init_db(app, config.database)
    init_qpu_client(app, config.qpu)
    init_auth(app, config.api)

    app.include_router(jobs.router, tags=["jobs"])
    app.include_router(sessions.router, tags=["sessions"])
    app.include_router(qpu.router, tags=["qpu"])
    app.include_router(accessible.router, tags=["accessible"])
    app.include_router(acct.router, tags=["accounting"])
    app.include_router(status.router, tags=["status"])

    logger = logging.getLogger(__name__)

    @app.get("/")
    async def ping():
        try:
            version = importlib.metadata.version("warden")
        except importlib.metadata.PackageNotFoundError:
            # `make install` only installs dependencies, so a source checkout
            # (e.g. the systemd setup) has no distribution metadata.
            try:
                pyproject = tomllib.loads(PYPROJECT.read_text())
                version = pyproject["tool"]["poetry"]["version"]
            except (OSError, KeyError, tomllib.TOMLDecodeError):
                version = ""
        return {"message": f"Warden {version} is operational."}

    logger.info("App ready")
    return app
