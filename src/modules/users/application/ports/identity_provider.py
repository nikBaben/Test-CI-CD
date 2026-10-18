from typing import Protocol
from datetime import date
from uuid import UUID

from src.modules.users.domain.auth import TokenPair


class IdentityProvider(Protocol):
    async def register(
        self, *, last_name: str, first_name: str, patronymic: str,
        phone_number: str, birthday: date, password: str,
    ) -> UUID: ...

    async def login(self, phone_number: str, password: str) -> TokenPair: ...

    async def refresh(self, refresh_token: str) -> TokenPair: ...

    async def delete_user(self, user_id: UUID) -> None: ...
