from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.users.application.exceptions import UserAlreadyExistsError, UserStorageError
from src.modules.users.domain.entities import User
from src.modules.users.infrastructure.database.models import UserORM


class SQLAlchemyUserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _to_user(row: UserORM | None) -> User | None:
        if row is None:
            return None
        return User(id=row.id, last_name=row.last_name, first_name=row.first_name,
                    patronymic=row.patronymic, phone_number=row.phone_number, birthday=row.birthday)

    async def get_by_id(self, user_id: UUID) -> User | None:
        try:
            return self._to_user(await self.session.get(UserORM, user_id))
        except SQLAlchemyError as exc:
            raise UserStorageError() from exc

    async def get_by_phone(self, phone_number: str) -> User | None:
        try:
            row = await self.session.scalar(select(UserORM).where(UserORM.phone_number == phone_number))
            return self._to_user(row)
        except SQLAlchemyError as exc:
            raise UserStorageError() from exc

    async def add(self, user: User) -> None:
        self.session.add(UserORM(**user.model_dump()))
        try:
            await self.session.flush()
        except IntegrityError as exc:
            if getattr(exc.orig, "sqlstate", None) == "23505":
                raise UserAlreadyExistsError() from exc
            raise UserStorageError() from exc
        except SQLAlchemyError as exc:
            raise UserStorageError() from exc
