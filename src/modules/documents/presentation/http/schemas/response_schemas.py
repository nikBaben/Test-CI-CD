from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from src.modules.documents.domain.enums import DocumentType


class CompanyDocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    company_id: UUID
    user_id: UUID
    document_type: DocumentType
    year: int
    filename: str
    size_bytes: int
    sha256: str
    created_at: datetime
    updated_at: datetime
