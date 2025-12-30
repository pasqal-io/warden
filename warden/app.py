import logging
import logging.config
from fastapi import FastAPI
from warden.api import jobs, sessions
from warden.config.config import Config
from warden.db.database import init_db


def create_app(config: Config = Config()):
    logging.config.dictConfig(config.logging)
    app = FastAPI(
        title="Warden API",
        description="Receives, validates, and stores jobs for execution",
        version="0.1.0",
    )
    init_db(app, config.database)

    app.include_router(jobs.router, tags=["jobs"])
    app.include_router(sessions.router, tags=["sessions"])

    logger = logging.getLogger(__name__)

    @app.get("/")
    async def ping():
        return {"message": "The warden is operational."}

    logger.info("App ready")
    return app


