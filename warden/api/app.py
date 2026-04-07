import logging

from fastapi import FastAPI

from warden.api.routes import accessible, jobs, qpu, sessions
from warden.api.routes.dependencies.db import init_db
from warden.api.routes.dependencies.qpu_client import init_qpu_client
from warden.lib.config import Config


def create_app(config: Config):
    app = FastAPI(
        title="Warden API",
        description="Receives, validates, and stores jobs for execution",
        version="0.1.0",
    )
    init_db(app, config.database)
    init_qpu_client(app, config.qpu)

    app.include_router(jobs.router, tags=["jobs"])
    app.include_router(sessions.router, tags=["sessions"])
    app.include_router(qpu.router, tags=["qpu"])
    app.include_router(accessible.router, tags=["accessible"])

    logger = logging.getLogger(__name__)

    @app.get("/")
    async def ping():
        return {"message": "The warden is operational."}

    logger.info("App ready")
    return app
