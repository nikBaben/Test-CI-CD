from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from src.modules.documents.domain.enums import DocumentType
from src.modules.documents.domain.validation import validate_reporting_year


@dataclass(frozen=True)
class CompanyDocument:
    id: UUID
    company_id: UUID
    user_id: UUID
    document_type: DocumentType
    year: int
    filename: str
    size_bytes: int
    sha256: str
    object_key: str
    created_at: datetime
    updated_at: datetime

    def __post_init__(self):
        validate_reporting_year(self.year)
