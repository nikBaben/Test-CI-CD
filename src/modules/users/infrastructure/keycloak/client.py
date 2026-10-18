from uuid import UUID
from datetime import date

import httpx

from src.shared.config import KeycloakSettings

from src.modules.users.domain.auth import TokenPair
from src.modules.users.application.exceptions import (
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    InvalidUserDataError,
    IdentityProviderPermissionError,
    IdentityProviderUnavailableError,
    IdentityProviderUnexpectedError,
    UserAlreadyExistsError,
)


class KeycloakClient:

    def __init__(
        self,
        http_client: httpx.AsyncClient,
        settings: KeycloakSettings,
    ):
        self.http_client = http_client
        self.settings = settings

        self.token_url = settings.token_url

        self.users_url = (
            f"{settings.keycloak_url.rstrip('/')}"
            f"/admin/realms/{settings.keycloak_realm}/users"
        )

    async def _post(
        self,
        url: str,
        **kwargs,
    ) -> httpx.Response:
        """Единый метод выполнения POST-запросов."""

        try:
            return await self.http_client.post(
                url,
                **kwargs,
            )
        except httpx.RequestError as exc:
            raise IdentityProviderUnavailableError() from exc

    @staticmethod
    def _parse_tokens(
        response: httpx.Response,
    ) -> TokenPair:
        """Преобразовать ответ Keycloak в доменную пару токенов."""

        try:
            return TokenPair.model_validate(
                response.json()
            )
        except (ValueError, TypeError) as exc:
            raise IdentityProviderUnexpectedError(
                "Некорректный ответ token endpoint"
            ) from exc

    @staticmethod
    def _get_error_code(
        response: httpx.Response,
    ) -> str | None:
        """Получить OAuth error из ответа Keycloak."""

        try:
            payload = response.json()
        except ValueError:
            return None

        if not isinstance(payload, dict):
            return None

        return payload.get("error")

    async def _request_token(
        self,
        grant_type: str,
        client_id: str,
        client_secret: str,
        **kwargs: str,
    ) -> httpx.Response:
        """Общая отправка запроса к token endpoint."""

        return await self._post(
            self.token_url,
            data={
                "grant_type": grant_type,
                "client_id": client_id,
                "client_secret": client_secret,
                **kwargs,
            },
        )

    async def _get_service_token(self) -> str:
        """Получить токен сервисного аккаунта."""

        response = await self._request_token(
            grant_type="client_credentials",
            client_id=(
                self.settings.keycloak_registration_client_id
            ),
            client_secret=(
                self.settings.keycloak_registration_client_secret.get_secret_value()
            ),
        )

        if response.status_code != 200:
            raise IdentityProviderUnexpectedError(
                "Не удалось получить служебный токен"
            )

        try:
            token = response.json()["access_token"]
            if not isinstance(token, str) or not token:
                raise ValueError("Empty service token")
            return token
        except (ValueError, KeyError, TypeError) as exc:
            raise IdentityProviderUnexpectedError(
                "Keycloak не вернул access_token"
            ) from exc

    async def login(
        self,
        phone_number: str,
        password: str,
    ) -> TokenPair:
        """Авторизация пользователя."""

        response = await self._request_token(
            grant_type="password",
            client_id=self.settings.keycloak_client_id,
            client_secret=self.settings.keycloak_client_secret.get_secret_value(),
            # Внешний API принимает phone_number, протокол Keycloak — username.
            username=phone_number,
            password=password,
        )

        if response.status_code == 200:
            return self._parse_tokens(response)

        if self._get_error_code(response) == "invalid_grant":
            raise InvalidCredentialsError()

        raise IdentityProviderUnexpectedError(
            "Ошибка авторизации в Keycloak"
        )

    async def register(
        self,
        *, last_name: str, first_name: str, patronymic: str,
        phone_number: str, birthday: date, password: str,
    ) -> UUID:
        """Создание пользователя через Admin API."""

        service_token = await self._get_service_token()

        response = await self._post(
            self.users_url,
            headers={
                "Authorization": f"Bearer {service_token}",
            },
            json={
                # Keycloak требует username; в приложении логин — номер телефона.
                "username": phone_number,
                "firstName": first_name,
                "lastName": last_name,
                "enabled": True,
                "attributes": {
                    "patronymic": [patronymic],
                    "phone_number": [phone_number],
                    "birthday": [birthday.isoformat()],
                },
                "credentials": [
                    {
                        "type": "password",
                        "value": password,
                        "temporary": False,
                    }
                ],
            },
        )

        if response.status_code == 409:
            raise UserAlreadyExistsError()

        if response.status_code == 400:
            raise InvalidUserDataError()

        if response.status_code == 403:
            raise IdentityProviderPermissionError()

        if response.status_code != 201:
            raise IdentityProviderUnexpectedError(
                "Ошибка создания пользователя"
            )

        location = response.headers.get("Location")

        if not location:
            raise IdentityProviderUnexpectedError(
                "Keycloak не вернул идентификатор пользователя"
            )

        try:
            return UUID(
                location.rstrip("/").split("/")[-1]
            )
        except ValueError as exc:
            raise IdentityProviderUnexpectedError(
                "Некорректный идентификатор пользователя"
            ) from exc

    async def refresh(
        self,
        refresh_token: str,
    ) -> TokenPair:
        """Обновить access token."""

        response = await self._request_token(
            grant_type="refresh_token",
            client_id=self.settings.keycloak_client_id,
            client_secret=self.settings.keycloak_client_secret.get_secret_value(),
            refresh_token=refresh_token,
        )

        if response.status_code == 200:
            return self._parse_tokens(response)

        if self._get_error_code(response) == "invalid_grant":
            raise InvalidRefreshTokenError()

        raise IdentityProviderUnexpectedError(
            "Ошибка обновления токенов"
        )

    async def delete_user(self, user_id: UUID) -> None:
        """Компенсация создания учётной записи при ошибке сохранения профиля."""
        token = await self._get_service_token()
        try:
            response = await self.http_client.delete(
                f"{self.users_url}/{user_id}", headers={"Authorization": f"Bearer {token}"},
            )
        except httpx.RequestError as exc:
            raise IdentityProviderUnavailableError() from exc
        if response.status_code not in (204, 404):
            raise IdentityProviderUnexpectedError("Не удалось отменить создание пользователя")
