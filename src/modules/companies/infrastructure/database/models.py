"""Компания пользователя и снимки её годовой финансовой отчётности."""
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from src.shared.database.base import Base


class CompanyORM(Base):
    __tablename__ = "companies"
    __table_args__ = (
        UniqueConstraint("user_id", "inn", name="uq_companies_user_inn"),
        UniqueConstraint("id", "user_id", name="uq_companies_id_user"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    inn: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sales_model: Mapped[str] = mapped_column(String(3), nullable=False)
    primary_sales_channel: Mapped[str] = mapped_column(String(64), nullable=False)
    tax_regime: Mapped[str] = mapped_column(String(16), nullable=False)
    key_vulnerability: Mapped[str] = mapped_column(String(64), nullable=False)
    seasonality: Mapped[str] = mapped_column(String(32), nullable=False)
    ceo_goal: Mapped[str] = mapped_column(String(128), nullable=False)
    ogrn: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    registered_at: Mapped[date | None]
    city: Mapped[str | None] = mapped_column(Text)
    employee_count: Mapped[int | None]
    primary_okved_class: Mapped[int] = mapped_column(nullable=False)
    primary_okved_name: Mapped[str] = mapped_column(Text, nullable=False)
    global_sector: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class CompanyEconomicSectorORM(Base):
    """Дополнительные виды деятельности в исходном порядке, включая одинаковые классы."""
    __tablename__ = "company_economic_sectors"
    __table_args__ = (CheckConstraint("position >= 0", name="ck_company_economic_sectors_position"),)

    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), primary_key=True)
    position: Mapped[int] = mapped_column(primary_key=True)
    class_okved: Mapped[int] = mapped_column(nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    global_sector: Mapped[str] = mapped_column(Text, nullable=False)


class CompanyFinanceORM(Base):
    __tablename__ = "companies_finance"
    __table_args__ = (CheckConstraint("year >= 1900", name="ck_companies_finance_year"),)

    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), primary_key=True)
    year: Mapped[int] = mapped_column(primary_key=True)
    revenue: Mapped[Decimal | None] = mapped_column(Numeric(28, 2))
    net_profit: Mapped[Decimal | None] = mapped_column(Numeric(28, 2))
    cost_of_sales: Mapped[Decimal | None] = mapped_column(Numeric(28, 2))
    gross_profit: Mapped[Decimal | None] = mapped_column(Numeric(28, 2))
    gross_profit_margin: Mapped[Decimal | None] = mapped_column(Numeric(28, 2))
    commercial_expenses: Mapped[Decimal | None] = mapped_column(Numeric(28, 2))
    administrative_expenses: Mapped[Decimal | None] = mapped_column(Numeric(28, 2))
    operating_expenses: Mapped[Decimal | None] = mapped_column(Numeric(28, 2))
    net_profit_margin: Mapped[Decimal | None] = mapped_column(Numeric(28, 2))
    operating_cash_flow: Mapped[Decimal | None] = mapped_column(Numeric(28, 2))
    current_ratio: Mapped[Decimal | None] = mapped_column(Numeric(28, 2))
    payroll_payments: Mapped[Decimal | None] = mapped_column(Numeric(28, 2))
    payroll_payment_share: Mapped[Decimal | None] = mapped_column(Numeric(28, 2))
    revenue_per_employee: Mapped[Decimal | None] = mapped_column(Numeric(28, 2))
    sales_expense_ratio: Mapped[Decimal | None] = mapped_column(Numeric(28, 2))
    cac: Mapped[Decimal | None] = mapped_column(Numeric(28, 2))
    ltv: Mapped[Decimal | None] = mapped_column(Numeric(28, 2))
