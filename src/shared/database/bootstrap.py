from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.shared.config import DatabaseSettings
from src.shared.database.session import create_database


@asynccontextmanager
async def database_lifespan(app: FastAPI, settings: DatabaseSettings):
    engine, session_factory = create_database(settings)
    app.state.session_factory = session_factory
    try:
        yield session_factory
    finally:
        del app.state.session_factory
        await engine.dispose()
