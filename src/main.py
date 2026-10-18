"""Точка входа API: poetry run uvicorn src.main:app --reload."""
from contextlib import AsyncExitStack, asynccontextmanager

import httpx
from fastapi import FastAPI

from src.modules.companies.infrastructure.bootstrap import companies_lifespan, configure_companies
from src.modules.documents.infrastructure.bootstrap import configure_documents, documents_lifespan
from src.modules.users.infrastructure.bootstrap import configure_users, users_lifespan
from src.shared.config import RabbitMQSettings, ServiceSettings
from src.shared.database.bootstrap import database_lifespan


def create_app(
    settings: ServiceSettings | None = None,
    *,
    keycloak_transport: httpx.AsyncBaseTransport | None = None,
    checko_transport: httpx.AsyncBaseTransport | None = None,
    rabbitmq_settings: RabbitMQSettings | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        config = settings if settings is not None else ServiceSettings()
        async with AsyncExitStack() as resources:
            await resources.enter_async_context(database_lifespan(app, config))
            await resources.enter_async_context(users_lifespan(app, config, transport=keycloak_transport))
            await resources.enter_async_context(companies_lifespan(
                app, config, transport=checko_transport, rabbitmq_settings=rabbitmq_settings,
            ))
            await resources.enter_async_context(documents_lifespan(app, config))
            yield

    app = FastAPI(title=settings.app_name if settings else "Account Service", lifespan=lifespan)
    configure_users(app)
    configure_companies(app)
    configure_documents(app)

    @app.get("/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
