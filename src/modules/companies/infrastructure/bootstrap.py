from contextlib import AsyncExitStack, asynccontextmanager

import httpx
from fastapi import FastAPI

from src.modules.companies.infrastructure.broker.bootstrap import messaging_lifespan
from src.modules.companies.infrastructure.checko.client import CheckoClient
from src.modules.companies.infrastructure.outbox.bootstrap import outbox_lifespan
from src.modules.companies.presentation.http.checko_router import router as checko_router
from src.modules.companies.presentation.http.exception_handlers import register_company_exception_handlers
from src.modules.companies.presentation.http.routers import router as companies_router
from src.shared.config import RabbitMQSettings, ServiceSettings


def configure_companies(app: FastAPI) -> None:
    register_company_exception_handlers(app)
    app.include_router(checko_router)
    app.include_router(companies_router)


@asynccontextmanager
async def companies_lifespan(
    app: FastAPI,
    settings: ServiceSettings,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    rabbitmq_settings: RabbitMQSettings | None = None,
):
    async with AsyncExitStack() as resources:
        client = await resources.enter_async_context(httpx.AsyncClient(
            base_url=settings.checko_base_url, timeout=settings.checko_timeout_seconds, transport=transport,
        ))
        key = settings.checko_api_key.get_secret_value() if settings.checko_api_key else None
        app.state.checko_client = CheckoClient(client, key) if key else None
        try:
            publishers = await resources.enter_async_context(messaging_lifespan(
                rabbitmq_settings, publish_timeout=settings.rabbitmq_publish_timeout_seconds,
            ))
            app.state.publishers = publishers
            try:
                dispatcher = await resources.enter_async_context(outbox_lifespan(
                    app.state.session_factory, publishers, settings,
                ))
                app.state.outbox_dispatcher = dispatcher
                try:
                    yield
                finally:
                    del app.state.outbox_dispatcher
            finally:
                del app.state.publishers
        finally:
            del app.state.checko_client
