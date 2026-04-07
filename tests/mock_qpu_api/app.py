"""Mock QPU API for Warden testing and development"""

from fastapi import FastAPI

from mock_qpu_api.routes import jobs, programs, system

PREFIX = "/api/v1"


def create_app():
    app = FastAPI(
        title="Mocked QPU API",
        description="",
        version="0.1.0",
    )

    app.include_router(prefix=PREFIX, router=jobs.router)
    app.include_router(prefix=PREFIX, router=programs.router)
    app.include_router(prefix=PREFIX, router=system.router)

    @app.get("/")
    async def ping():
        return {"message", "Mocked QPU API is up."}

    return app


# Only creating app object if called from root of repo
# with makefile target
if __name__ == "mock_qpu_api.app":
    app = create_app()
