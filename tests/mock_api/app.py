from fastapi import FastAPI

from .routes import jobs, programs, system


def create_app():
    app = FastAPI(
        title="Mocked PasqOS API",
        description="",
        version="0.1.0",
    )

    app.include_router(prefix="/api/v1", router=jobs.router)
    app.include_router(prefix="/api/v1", router=programs.router)
    app.include_router(prefix="/api/v1", router=system.router)

    @app.get("/")
    async def hello():
        return {"message", "Mocked PasqOS API is up."}
    
    return app

app = create_app()

if __name__=="__main__":
    app = create_app()