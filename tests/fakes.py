from uuid import UUID

from src.modules.users.domain.entities import User


class MemoryUserUnitOfWork:
    def __init__(self):
        self.users = self
        self.stored: dict[UUID, User] = {}
        self.pending: dict[UUID, User] = {}
        self.add_error: Exception | None = None
        self.commit_error: Exception | None = None
        self.committed = False
        self.rolled_back = False

    async def get_by_id(self, user_id: UUID) -> User | None:
        return self.pending.get(user_id) or self.stored.get(user_id)

    async def get_by_phone(self, phone_number: str) -> User | None:
        return next((user for user in [*self.stored.values(), *self.pending.values()] if user.phone_number == phone_number), None)

    async def add(self, user: User) -> None:
        if self.add_error:
            raise self.add_error
        self.pending[user.id] = user

    async def commit(self) -> None:
        if self.commit_error:
            raise self.commit_error
        self.stored.update(self.pending)
        self.pending.clear()
        self.committed = True

    async def rollback(self) -> None:
        self.pending.clear()
        self.rolled_back = True
