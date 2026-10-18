from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.companies.application.exceptions import CompanyStorageError


class SQLAlchemyCompanyUnitOfWork:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def commit(self) -> None:
        try:
            await self.session.commit()
        except SQLAlchemyError as exc:
            raise CompanyStorageError() from exc

    async def rollback(self) -> None:
        try:
            await self.session.rollback()
        except SQLAlchemyError as exc:
            raise CompanyStorageError() from exc
