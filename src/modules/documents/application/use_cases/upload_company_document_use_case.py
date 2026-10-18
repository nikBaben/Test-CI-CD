import asyncio
import logging
from datetime import datetime, timezone
from uuid import uuid4

from src.modules.documents.application.dto import CompanyDocumentDTO, UploadCompanyDocumentDTO
from src.modules.documents.application.mappers import document_to_dto
from src.modules.documents.application.ports.document_storage import DocumentStorage
from src.modules.documents.application.ports.document_unit_of_work import DocumentUnitOfWork
from src.modules.documents.domain.entities import CompanyDocument
from src.modules.documents.domain.exceptions import DocumentCompanyNotFoundError, DocumentStorageError
from src.modules.documents.domain.repositories import DocumentRepository
from src.modules.documents.domain.validation import validate_pdf, validate_reporting_year

logger = logging.getLogger(__name__)


class UploadCompanyDocumentUseCase:
    def __init__(self, repository: DocumentRepository, uow: DocumentUnitOfWork,
                 storage: DocumentStorage, max_bytes: int):
        self.repository, self.uow, self.storage, self.max_bytes = repository, uow, storage, max_bytes

    async def execute(self, data: UploadCompanyDocumentDTO) -> CompanyDocumentDTO:
        object_key = None
        commit_started = False
        try:
            if not await self.repository.lock_owned_company(data.user_id, data.company_id, write=True):
                raise DocumentCompanyNotFoundError()
            validate_reporting_year(data.year)
            validating = asyncio.create_task(asyncio.to_thread(
                validate_pdf, data.content, data.filename, data.content_type, self.max_bytes,
            ))
            try:
                pdf = await asyncio.shield(validating)
            except asyncio.CancelledError:
                # HTTP-слой закроет файл только после завершения чтения в рабочем потоке.
                try:
                    await validating
                except Exception:
                    pass
                raise
            current = await self.repository.get(data.user_id, data.company_id, data.document_type, data.year)
            now = datetime.now(timezone.utc)
            # Новый ключ при каждой загрузке: не перезаписываем действующий файл до commit.
            object_key = f"{data.user_id}/{data.company_id}/{uuid4()}.pdf"
            document = CompanyDocument(
                id=current.id if current else uuid4(), user_id=data.user_id, company_id=data.company_id,
                document_type=data.document_type, year=data.year, filename=pdf.filename,
                size_bytes=pdf.size_bytes, sha256=pdf.sha256, object_key=object_key,
                created_at=current.created_at if current else now, updated_at=now,
            )
            await self.storage.put(object_key, data.content, pdf.size_bytes)
            await self.repository.save(document)
            commit_started = True
            await self.uow.commit()
        except BaseException:
            await self.uow.rollback()
            # После сетевой ошибки commit мог всё же состояться. Удалять новый PDF небезопасно.
            # Периодическая сверка хранилища с БД уберёт только неподтверждённые объекты.
            if object_key and not commit_started:
                try:
                    await self.storage.delete(object_key)
                except DocumentStorageError:
                    logger.warning("Очистка незавершённой загрузки отложена")
            raise
        if current:
            try:
                await self.storage.delete(current.object_key)
            except DocumentStorageError:
                # Запись уже сохранена. Повторная очистка выполняется обслуживающей задачей.
                logger.warning("Очистка предыдущего PDF отложена: document_id=%s", document.id)
        return document_to_dto(document)
