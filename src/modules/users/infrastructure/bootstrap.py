from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from src.modules.users.infrastructure.keycloak.client import KeycloakClient
from src.modules.users.infrastructure.keycloak.provider import KeycloakProvider
from src.modules.users.presentation.http.exception_handlers import register_exception_handlers
from src.modules.users.presentation.http.routers import auth_router, users_router
from src.shared.config import KeycloakSettings
from src.shared.security.jwt_verifier import JWTVerifier


def configure_users(app: FastAPI) -> None:
    register_exception_handlers(app)
    app.include_router(auth_router)
    app.include_router(users_router)


@asynccontextmanager
async def users_lifespan(
    app: FastAPI,
    settings: KeycloakSettings,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
):
    async with httpx.AsyncClient(timeout=settings.keycloak_timeout_seconds, transport=transport) as client:
        app.state.identity_provider = KeycloakProvider(KeycloakClient(client, settings))
        app.state.jwt_verifier = JWTVerifier(settings)
        try:
            yield
        finally:
            del app.state.identity_provider
            del app.state.jwt_verifier
