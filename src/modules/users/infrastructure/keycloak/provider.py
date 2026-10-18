from uuid import UUID
from datetime import date

from src.modules.users.domain.auth import TokenPair
from src.modules.users.infrastructure.keycloak.client import KeycloakClient


class KeycloakProvider:
    """Реализация IdentityProvider поверх клиента Keycloak."""
    def __init__(self, client: KeycloakClient) -> None:
        self.client = client

    async def register(
        self, *, last_name: str, first_name: str, patronymic: str,
        phone_number: str, birthday: date, password: str,
    ) -> UUID:
        return await self.client.register(
            last_name=last_name, first_name=first_name, patronymic=patronymic,
            phone_number=phone_number, birthday=birthday, password=password,
        )

    async def login(self, phone_number: str, password: str) -> TokenPair:
        return await self.client.login(phone_number, password)

    async def refresh(self, refresh_token: str) -> TokenPair:
        return await self.client.refresh(refresh_token)

    async def delete_user(self, user_id: UUID) -> None:
        await self.client.delete_user(user_id)
