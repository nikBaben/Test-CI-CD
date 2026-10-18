from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.documents.domain.exceptions import DocumentStorageError


class SQLAlchemyDocumentUnitOfWork:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def commit(self) -> None:
        try:
            await self.session.commit()
        except SQLAlchemyError as exc:
            raise DocumentStorageError("Не удалось подтвердить сохранение документа") from exc

    async def rollback(self) -> None:
        try:
            await self.session.rollback()
        except SQLAlchemyError as exc:
            raise DocumentStorageError("Не удалось откатить транзакцию документа") from exc
