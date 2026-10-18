from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.modules.users.application.exceptions import (
    IdentityProviderError, InvalidCredentialsError, InvalidRefreshTokenError,
    InvalidUserDataError, IdentityProviderPermissionError, IdentityProviderUnavailableError,
    UserAlreadyExistsError,
    RegistrationIncompleteError, UserProfileNotFoundError, UserStorageError,
)


async def identity_error_handler(request: Request, exc: IdentityProviderError) -> JSONResponse:
    status, detail = 502, "Ошибка настройки или ответа Keycloak"
    if isinstance(exc, InvalidCredentialsError):
        status, detail = 401, "Вход отклонён: проверь логин, пароль и готовность учётной записи"
    elif isinstance(exc, InvalidRefreshTokenError):
        status, detail = 401, "Refresh token недействителен: нужно войти заново"
    elif isinstance(exc, UserAlreadyExistsError):
        status, detail = 409, "Пользователь с таким номером телефона уже существует"
    elif isinstance(exc, InvalidUserDataError):
        status, detail = 422, "Keycloak отклонил данные пользователя или пароль"
    elif isinstance(exc, IdentityProviderPermissionError):
        detail = "У сервисного аккаунта нет необходимых прав на создание пользователя"
    elif isinstance(exc, IdentityProviderUnavailableError):
        status, detail = 503, "Не удалось связаться с Keycloak"
    elif isinstance(exc, UserStorageError):
        status, detail = 503, "База данных приложения недоступна"
    elif isinstance(exc, RegistrationIncompleteError):
        status, detail = 503, "Регистрация требует восстановления профиля; обратись к администратору"
    elif isinstance(exc, UserProfileNotFoundError):
        status, detail = 404, "Профиль пользователя не найден"
    return JSONResponse(
        status_code=status, content={"detail": detail},
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(IdentityProviderError, identity_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Стандартный ответ 422 включает input: туда могут попасть пароль или refresh token.
    errors = [{key: error[key] for key in ("loc", "msg", "type")} for error in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": errors}, headers={"Cache-Control": "no-store"})
