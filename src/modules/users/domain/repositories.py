from typing import Protocol
from uuid import UUID

from src.modules.users.domain.entities import User


class UserRepository(Protocol):
    async def get_by_id(self, user_id: UUID) -> User | None: ...

    async def get_by_phone(self, phone_number: str) -> User | None: ...

    async def add(self, user: User) -> None: ...
