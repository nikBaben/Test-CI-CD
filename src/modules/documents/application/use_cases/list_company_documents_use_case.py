from src.modules.documents.application.dto import CompanyDocumentDTO, ListCompanyDocumentsDTO
from src.modules.documents.application.mappers import document_to_dto
from src.modules.documents.application.ports.document_unit_of_work import DocumentUnitOfWork
from src.modules.documents.domain.exceptions import DocumentCompanyNotFoundError
from src.modules.documents.domain.repositories import DocumentRepository


class ListCompanyDocumentsUseCase:
    def __init__(self, repository: DocumentRepository, uow: DocumentUnitOfWork):
        self.repository, self.uow = repository, uow

    async def execute(self, data: ListCompanyDocumentsDTO) -> list[CompanyDocumentDTO]:
        try:
            if not await self.repository.lock_owned_company(data.user_id, data.company_id, write=False):
                raise DocumentCompanyNotFoundError()
            documents = await self.repository.list(data.user_id, data.company_id)
            await self.uow.commit()
            return [document_to_dto(document) for document in documents]
        except BaseException:
            await self.uow.rollback()
            raise
