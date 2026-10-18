from src.modules.documents.application.dto import DownloadCompanyDocumentDTO, GetCompanyDocumentDTO
from src.modules.documents.application.mappers import document_to_dto
from src.modules.documents.application.ports.document_storage import DocumentStorage
from src.modules.documents.application.ports.document_unit_of_work import DocumentUnitOfWork
from src.modules.documents.domain.exceptions import DocumentCompanyNotFoundError, DocumentNotFoundError
from src.modules.documents.domain.repositories import DocumentRepository
from src.modules.documents.domain.validation import validate_reporting_year


class GetCompanyDocumentUseCase:
    def __init__(self, repository: DocumentRepository, uow: DocumentUnitOfWork, storage: DocumentStorage):
        self.repository, self.uow, self.storage = repository, uow, storage

    async def execute(self, data: GetCompanyDocumentDTO) -> DownloadCompanyDocumentDTO:
        content = None
        try:
            if not await self.repository.lock_owned_company(data.user_id, data.company_id, write=False):
                raise DocumentCompanyNotFoundError()
            validate_reporting_year(data.year)
            document = await self.repository.get(data.user_id, data.company_id, data.document_type, data.year)
            if document is None:
                raise DocumentNotFoundError()
            # Читаем в ограниченный временный файл под FOR SHARE. Замена не удалит PDF во время чтения.
            content = await self.storage.get(document.object_key, document.size_bytes, document.sha256)
            await self.uow.commit()
            return DownloadCompanyDocumentDTO(document=document_to_dto(document), content=content)
        except BaseException:
            if content is not None:
                content.close()
            await self.uow.rollback()
            raise
