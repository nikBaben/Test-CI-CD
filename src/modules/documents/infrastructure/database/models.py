from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.shared.database.base import Base


class CompanyDocumentORM(Base):
    __tablename__ = "company_documents"
    __table_args__ = (
        ForeignKeyConstraint(["company_id", "user_id"], ["companies.id", "companies.user_id"], ondelete="CASCADE",
                             name="fk_company_documents_owned_company"),
        UniqueConstraint("company_id", "document_type", "year", name="uq_company_documents_type_year"),
        CheckConstraint("year BETWEEN 1900 AND 9999", name="ck_company_documents_year"),
        CheckConstraint("size_bytes > 0", name="ck_company_documents_size"),
        CheckConstraint("document_type IN ('balance_sheet', 'financial_results', 'changes_in_equity', 'cash_flows', 'targeted_funds')",
                        name="ck_company_documents_type"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    company_id: Mapped[UUID] = mapped_column(nullable=False)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    document_type: Mapped[str] = mapped_column(String(32), nullable=False)
    year: Mapped[int] = mapped_column(nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    object_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
