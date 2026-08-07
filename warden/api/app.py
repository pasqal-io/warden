import logging

from fastapi import FastAPI

from warden.api.routes import accessible, acct, jobs, qpu, sessions
from warden.api.routes.dependencies.auth import init_auth
from warden.api.routes.dependencies.db import init_db
from warden.api.routes.dependencies.qpu_client import init_qpu_client
from warden.lib.config import Config

TAGS_METADATA = [
    {
        "name": "accounting",
        "description": "Accounting endpoints for Warden usage report generation."
    }
]

def create_app(config: Config):
    app = FastAPI(
        title="Warden API",
        description="Receives, validates, and stores jobs for execution",
        version="0.2.0",
        openapi_tags=TAGS_METADATA
    )
    init_db(app, config.database)
    init_qpu_client(app, config.qpu)
    init_auth(app, config.api)

    app.include_router(jobs.router, tags=["jobs"])
    app.include_router(sessions.router, tags=["sessions"])
    app.include_router(qpu.router, tags=["qpu"])
    app.include_router(accessible.router, tags=["accessible"])
    app.include_router(acct.router, tags=["accounting"])

    logger = logging.getLogger(__name__)

    @app.get("/")
    async def ping():
        return {"message": "The warden is operational."}

    logger.info("App ready")
    return app
