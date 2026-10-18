"""Транспорт между HTTP-ручками и use case; UploadFile здесь не используется."""
from dataclasses import dataclass
from datetime import datetime
from typing import BinaryIO
from uuid import UUID

from src.modules.documents.domain.enums import DocumentType


@dataclass(frozen=True)
class UploadCompanyDocumentDTO:
    user_id: UUID
    company_id: UUID
    document_type: DocumentType
    year: int
    filename: str
    content_type: str
    content: BinaryIO


@dataclass(frozen=True)
class GetCompanyDocumentDTO:
    user_id: UUID
    company_id: UUID
    document_type: DocumentType
    year: int


@dataclass(frozen=True)
class ListCompanyDocumentsDTO:
    user_id: UUID
    company_id: UUID


@dataclass(frozen=True)
class CompanyDocumentDTO:
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


@dataclass(frozen=True)
class DownloadCompanyDocumentDTO:
    document: CompanyDocumentDTO
    content: BinaryIO
