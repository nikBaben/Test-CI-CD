from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.documents.application.ports.document_storage import DocumentStorage
from src.modules.documents.application.ports.document_unit_of_work import DocumentUnitOfWork
from src.modules.documents.application.use_cases.get_company_document_use_case import GetCompanyDocumentUseCase
from src.modules.documents.application.use_cases.list_company_documents_use_case import ListCompanyDocumentsUseCase
from src.modules.documents.application.use_cases.upload_company_document_use_case import UploadCompanyDocumentUseCase
from src.modules.documents.domain.exceptions import DocumentStorageError
from src.modules.documents.domain.repositories import DocumentRepository
from src.modules.documents.infrastructure.database.repositories import SQLAlchemyDocumentRepository
from src.modules.documents.infrastructure.database.unit_of_work import SQLAlchemyDocumentUnitOfWork
from src.shared.database.session import get_session


def get_document_storage(request: Request) -> DocumentStorage:
    if request.app.state.document_storage is None:
        raise DocumentStorageError("Не настроено хранилище документов")
    return request.app.state.document_storage


def get_document_repository(session: Annotated[AsyncSession, Depends(get_session)]) -> DocumentRepository:
    return SQLAlchemyDocumentRepository(session)


def get_document_uow(session: Annotated[AsyncSession, Depends(get_session)]) -> DocumentUnitOfWork:
    return SQLAlchemyDocumentUnitOfWork(session)


RepositoryDep = Annotated[DocumentRepository, Depends(get_document_repository)]
UnitOfWorkDep = Annotated[DocumentUnitOfWork, Depends(get_document_uow)]
StorageDep = Annotated[DocumentStorage, Depends(get_document_storage)]


def get_upload_company_document(request: Request, repository: RepositoryDep, uow: UnitOfWorkDep,
                                storage: StorageDep) -> UploadCompanyDocumentUseCase:
    return UploadCompanyDocumentUseCase(repository, uow, storage, request.app.state.document_max_bytes)


def get_company_document(repository: RepositoryDep, uow: UnitOfWorkDep, storage: StorageDep) -> GetCompanyDocumentUseCase:
    return GetCompanyDocumentUseCase(repository, uow, storage)


def get_list_company_documents(repository: RepositoryDep, uow: UnitOfWorkDep) -> ListCompanyDocumentsUseCase:
    return ListCompanyDocumentsUseCase(repository, uow)
