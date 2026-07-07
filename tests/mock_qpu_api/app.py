"""Mock QPU API for Warden testing and development"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from mock_qpu_api.routes import jobs, system
from mock_qpu_api.routes.dependencies.qutip_emul import init_qutip_emul
from mock_qpu_api.routes.dependencies.timed_job import init_timed_job
from mock_qpu_api.routes.exception import JobCancelationError

PREFIX = "/api/v1"


def create_app():
    app = FastAPI(
        title="Mocked QPU API",
        description="",
        version="0.1.0",
    )

    init_timed_job(app)
    init_qutip_emul(app)

    app.include_router(prefix=PREFIX, router=jobs.router)
    app.include_router(prefix=PREFIX, router=system.router)

    @app.exception_handler(JobCancelationError)
    async def job_cancelation_exception_handler(
        request: Request, exc: JobCancelationError
    ):
        """Custom handling of job cancellation errors to mimick QPU behavior."""
        return JSONResponse(
            status_code=400,
            content={
                "code": "OSPG3003",
                "data": {
                    "description": "Cannot cancel program.",
                    "status": str(exc.job_status),
                },
                "message": "Bad request",
                "status": "fail",
            },
        )

    @app.get("/")
    async def ping():
        return {"message", "Mocked QPU API is up."}

    return app


# Only creating app object if called from root of repo
# with makefile target
if __name__ == "mock_qpu_api.app":
    app = create_app()
