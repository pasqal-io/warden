from typing import Annotated, AsyncGenerator

from fastapi import Depends, FastAPI, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from warden.lib.config import DatabaseConfig
from warden.lib.db.database import build_engine


def init_db(app: FastAPI, db_config: DatabaseConfig):
    """Initialize the async engine and session factory with the given DB URL."""
    engine = build_engine(db_config)

    # TODO: ensure isolation between concurrent requests
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

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
