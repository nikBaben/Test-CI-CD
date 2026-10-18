import asyncio
from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import StreamingResponse

from src.modules.documents.application.dto import GetCompanyDocumentDTO, ListCompanyDocumentsDTO, UploadCompanyDocumentDTO
from src.modules.documents.application.use_cases.get_company_document_use_case import GetCompanyDocumentUseCase
from src.modules.documents.application.use_cases.list_company_documents_use_case import ListCompanyDocumentsUseCase
from src.modules.documents.application.use_cases.upload_company_document_use_case import UploadCompanyDocumentUseCase
from src.modules.documents.domain.enums import DocumentType
from src.modules.documents.domain.validation import ReportingYear
from src.modules.documents.infrastructure.deps import get_company_document, get_list_company_documents, get_upload_company_document
from src.modules.documents.presentation.http.schemas.request_schemas import UploadCompanyDocumentRequest
from src.modules.documents.presentation.http.schemas.response_schemas import CompanyDocumentResponse
from src.modules.users.infrastructure.deps import CurrentUserDep

router = APIRouter(prefix="/companies/{company_id}/documents", tags=["company documents"])


def owner_id(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError:
        raise HTTPException(401, "Некорректный идентификатор пользователя", headers={"WWW-Authenticate": "Bearer"}) from None


@router.put("/{document_type}/{year}", response_model=CompanyDocumentResponse,
            summary="Загрузить или заменить PDF за отчётный год")
async def upload_company_document_handler(
    company_id: UUID, document_type: DocumentType, year: ReportingYear, user: CurrentUserDep,
    payload: Annotated[UploadCompanyDocumentRequest, Form(media_type="multipart/form-data")],
    use_case: Annotated[UploadCompanyDocumentUseCase, Depends(get_upload_company_document)],
):
    try:
        result = await use_case.execute(UploadCompanyDocumentDTO(
            user_id=owner_id(user.user_id), company_id=company_id, document_type=document_type, year=year,
            filename=payload.file.filename or "", content_type=payload.file.content_type or "",
            content=payload.file.file,
        ))
        return CompanyDocumentResponse.model_validate(result)
    finally:
        await payload.file.close()


@router.get("", response_model=list[CompanyDocumentResponse], summary="Список документов своей компании")
async def list_company_documents_handler(
    company_id: UUID, user: CurrentUserDep,
    use_case: Annotated[ListCompanyDocumentsUseCase, Depends(get_list_company_documents)],
):
    documents = await use_case.execute(ListCompanyDocumentsDTO(user_id=owner_id(user.user_id), company_id=company_id))
    return [CompanyDocumentResponse.model_validate(document) for document in documents]


class PDFResponse(StreamingResponse):
    def __init__(self, content, **kwargs):
        self.file = content

        def chunks():
            while chunk := content.read(64 * 1024):
                yield chunk

        super().__init__(chunks(), **kwargs)

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            await asyncio.to_thread(self.file.close)


@router.get("/{document_type}/{year}", response_class=StreamingResponse,
            responses={200: {"content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}}}},
            summary="Скачать PDF своей компании через API")
async def get_company_document_handler(
    company_id: UUID, document_type: DocumentType, year: ReportingYear, user: CurrentUserDep,
    use_case: Annotated[GetCompanyDocumentUseCase, Depends(get_company_document)],
):
    result = await use_case.execute(GetCompanyDocumentDTO(
        user_id=owner_id(user.user_id), company_id=company_id, document_type=document_type, year=year,
    ))
    document = result.document
    return PDFResponse(result.content, media_type="application/pdf", headers={
        "Content-Disposition": f"attachment; filename=\"document.pdf\"; filename*=UTF-8''{quote(document.filename, safe='')}",
        "Content-Length": str(document.size_bytes), "ETag": f'"{document.sha256}"',
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
    })
