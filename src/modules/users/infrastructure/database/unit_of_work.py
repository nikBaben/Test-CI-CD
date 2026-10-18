from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.users.application.exceptions import UserStorageError
from src.modules.users.infrastructure.database.repositories import SQLAlchemyUserRepository


class SQLAlchemyUserUnitOfWork:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.users = SQLAlchemyUserRepository(session)

    async def commit(self) -> None:
        try:
            await self.session.commit()
        except SQLAlchemyError as exc:
            raise UserStorageError() from exc

    async def rollback(self) -> None:
        try:
            await self.session.rollback()
        except SQLAlchemyError as exc:
            raise UserStorageError() from exc
