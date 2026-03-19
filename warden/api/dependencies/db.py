from typing import Annotated, AsyncGenerator
from fastapi import Depends, Request, FastAPI
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from warden.config.config import DatabaseConfig
from warden.db.database import build_db_url


def init_db(app: FastAPI, db_config: DatabaseConfig):
    """Initialize the async engine and session factory with the given DB URL."""
    engine = create_async_engine(build_db_url(db_config), echo=db_config.echo)

    # TODO: ensure isolation between concurrent requests
    session_factory = sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )

    app.state.db_engine = engine
    app.state.db_session_factory = session_factory


async def get_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency to provide a database session."""
    session_factory = getattr(request.app.state, "db_session_factory", None)
    if session_factory is None:
        raise RuntimeError(
            "Database not initialized. init_db(app, ...) was not called."
        )

    async with session_factory() as session:
        yield session


DBSessionDep = Annotated[AsyncSession, Depends(get_session)]
