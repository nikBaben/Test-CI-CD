from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.users.domain.auth import CurrentUser
from src.modules.users.application.ports.identity_provider import IdentityProvider
from src.modules.users.application.ports.user_unit_of_work import UserUnitOfWork
from src.modules.users.application.use_cases.login_user_use_case import LoginUserUseCase
from src.modules.users.application.use_cases.refresh_tokens_use_case import RefreshTokensUseCase
from src.modules.users.application.use_cases.register_user_use_case import RegisterUserUseCase
from src.modules.users.application.use_cases.get_user_profile_use_case import GetUserProfileUseCase
from src.modules.users.infrastructure.database.unit_of_work import SQLAlchemyUserUnitOfWork
from src.shared.database.session import get_session
from src.shared.security.jwt_verifier import (
    InvalidAccessTokenError, JWKSUnavailableError, JWTVerifier,
)

bearer = HTTPBearer(auto_error=False, bearerFormat="JWT")


def get_identity_provider(request: Request) -> IdentityProvider:
    return request.app.state.identity_provider


def get_user_uow(session: Annotated[AsyncSession, Depends(get_session)]) -> UserUnitOfWork:
    return SQLAlchemyUserUnitOfWork(session)


def get_register_user(
    provider: Annotated[IdentityProvider, Depends(get_identity_provider)],
    uow: Annotated[UserUnitOfWork, Depends(get_user_uow)],
) -> RegisterUserUseCase:
    return RegisterUserUseCase(provider, uow)


def get_user_profile(uow: Annotated[UserUnitOfWork, Depends(get_user_uow)]) -> GetUserProfileUseCase:
    return GetUserProfileUseCase(uow)


def get_login_user(provider: Annotated[IdentityProvider, Depends(get_identity_provider)]) -> LoginUserUseCase:
    return LoginUserUseCase(provider)


def get_refresh_tokens(provider: Annotated[IdentityProvider, Depends(get_identity_provider)]) -> RefreshTokensUseCase:
    return RefreshTokensUseCase(provider)


def get_jwt_verifier(request: Request) -> JWTVerifier:
    return request.app.state.jwt_verifier


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    verifier: Annotated[JWTVerifier, Depends(get_jwt_verifier)],
) -> CurrentUser:
    # Обычная def: синхронный PyJWKClient работает в thread pool FastAPI.
    if credentials is None:
        raise HTTPException(401, "Передай access token", headers={"WWW-Authenticate": "Bearer"})
    try:
        claims = verifier.verify(credentials.credentials)
    except InvalidAccessTokenError:
        raise HTTPException(401, "Токен недействителен или истёк", headers={"WWW-Authenticate": "Bearer"}) from None
    except JWKSUnavailableError:
        raise HTTPException(503, "Не удалось получить публичные ключи Keycloak") from None

    def optional_text(name: str) -> str | None:
        value = claims.get(name)
        return value if isinstance(value, str) else None

    return CurrentUser(
        user_id=claims["sub"], username=optional_text("preferred_username"),
        email=optional_text("email"), first_name=optional_text("given_name"),
        last_name=optional_text("family_name"),
    )


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
