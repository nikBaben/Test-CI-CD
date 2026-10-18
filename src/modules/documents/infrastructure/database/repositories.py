from contextlib import asynccontextmanager
from dataclasses import asdict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.companies.infrastructure.database.models import CompanyORM
from src.modules.documents.domain.entities import CompanyDocument
from src.modules.documents.domain.enums import DocumentType
from src.modules.documents.domain.exceptions import DocumentStorageError
from src.modules.documents.infrastructure.database.models import CompanyDocumentORM


@asynccontextmanager
async def database_errors():
    try:
        yield
    except SQLAlchemyError as exc:
        raise DocumentStorageError("Не удалось прочитать или сохранить метаданные документа") from exc


def to_entity(row: CompanyDocumentORM) -> CompanyDocument:
    return CompanyDocument(
        id=row.id, company_id=row.company_id, user_id=row.user_id,
        document_type=DocumentType(row.document_type), year=row.year,
        filename=row.filename, size_bytes=row.size_bytes, sha256=row.sha256,
        object_key=row.object_key, created_at=row.created_at, updated_at=row.updated_at,
    )


class SQLAlchemyDocumentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def lock_owned_company(self, user_id: UUID, company_id: UUID, *, write: bool) -> bool:
        async with database_errors():
            company = await self.session.scalar(select(CompanyORM.id).where(
                CompanyORM.id == company_id, CompanyORM.user_id == user_id,
            ).with_for_update(read=not write))
            return company is not None

    async def get(self, user_id: UUID, company_id: UUID, document_type: DocumentType, year: int) -> CompanyDocument | None:
        async with database_errors():
            row = await self.session.scalar(select(CompanyDocumentORM).where(
                CompanyDocumentORM.user_id == user_id, CompanyDocumentORM.company_id == company_id,
                CompanyDocumentORM.document_type == document_type.value, CompanyDocumentORM.year == year,
            ).execution_options(populate_existing=True))
            return to_entity(row) if row else None

    async def list(self, user_id: UUID, company_id: UUID) -> list[CompanyDocument]:
        async with database_errors():
            rows = await self.session.scalars(select(CompanyDocumentORM).where(
                CompanyDocumentORM.user_id == user_id, CompanyDocumentORM.company_id == company_id,
            ).order_by(CompanyDocumentORM.year.desc(), CompanyDocumentORM.document_type))
            return [to_entity(row) for row in rows]

    async def save(self, document: CompanyDocument) -> None:
        async with database_errors():
            row = await self.session.scalar(select(CompanyDocumentORM).where(
                CompanyDocumentORM.id == document.id, CompanyDocumentORM.user_id == document.user_id,
                CompanyDocumentORM.company_id == document.company_id,
            ))
            values = asdict(document)
            values["document_type"] = document.document_type.value
            if row is None:
                self.session.add(CompanyDocumentORM(**values))
            else:
                for name, value in values.items():
                    setattr(row, name, value)
            await self.session.flush()
