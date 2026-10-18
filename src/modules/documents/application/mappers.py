from src.modules.documents.application.dto import CompanyDocumentDTO
from src.modules.documents.domain.entities import CompanyDocument


def document_to_dto(document: CompanyDocument) -> CompanyDocumentDTO:
    return CompanyDocumentDTO(
        id=document.id, company_id=document.company_id, user_id=document.user_id,
        document_type=document.document_type, year=document.year,
        filename=document.filename, size_bytes=document.size_bytes, sha256=document.sha256,
        created_at=document.created_at, updated_at=document.updated_at,
    )
