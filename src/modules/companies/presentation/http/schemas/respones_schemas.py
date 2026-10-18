"""Схемы ответов HTTP API companies; не зависят от DTO и доменных сущностей."""
from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from src.modules.companies.domain.enums import SalesModel, PrimarySalesChannel, TaxRegime, KeyVulnerability, Seasonality, CEOGoal, EconomicsSectors


class _Response(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class EconomicSectorResponse(_Response):
    classOkved: int
    name: str
    globalSector: EconomicsSectors


class CompanyInfoResponse(_Response):
    ogrn: str
    name: str
    full_name: str
    registered_at: date | None = None
    city: str | None = None
    economicSectorCompany: list[EconomicSectorResponse]
    primaryEconomicSectorCompany: EconomicSectorResponse
    employee_count: int | None = None


class FinancialInfoResponse(_Response):
    year: int
    revenue: Decimal | None = None
    net_profit: Decimal | None = None
    cost_of_sales: Decimal | None = None
    gross_profit: Decimal | None = None
    gross_profit_margin: Decimal | None = None
    commercial_expenses: Decimal | None = None
    administrative_expenses: Decimal | None = None
    operating_expenses: Decimal | None = None
    net_profit_margin: Decimal | None = None
    operating_cash_flow: Decimal | None = None
    current_ratio: Decimal | None = None
    payroll_payments: Decimal | None = None
    payroll_payment_share: Decimal | None = None
    revenue_per_employee: Decimal | None = None
    sales_expense_ratio: Decimal | None = None
    cac: Decimal | None = None
    ltv: Decimal | None = None


class CompanyDetailsResponse(_Response):
    inn: int
    salesModel: SalesModel
    primarySalesChannel: PrimarySalesChannel
    taxRegime: TaxRegime
    keyVulnerability: KeyVulnerability
    seasonality: Seasonality
    CEOGoal: CEOGoal
    infoCompany: CompanyInfoResponse
    financials: FinancialInfoResponse


class CompanyResponse(_Response):
    id: UUID
    company: CompanyDetailsResponse


class CheckoCompanyResponse(_Response):
    inn: int
    infoCompany: CompanyInfoResponse
    financials: FinancialInfoResponse | None
