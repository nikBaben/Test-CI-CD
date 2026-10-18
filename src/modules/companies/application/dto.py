"""Входные и выходные данные границы router ↔ use case."""
from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from src.modules.companies.domain.enums import SalesModel, PrimarySalesChannel, TaxRegime, KeyVulnerability, Seasonality, CEOGoal, EconomicsSectors
from src.modules.companies.domain.validation import CompanyINN


class _DTO(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CreateCompanyDTO(_DTO):
    user_id: UUID
    inn: CompanyINN
    sales_model: SalesModel
    primary_sales_channel: PrimarySalesChannel
    tax_regime: TaxRegime
    key_vulnerability: KeyVulnerability
    seasonality: Seasonality
    ceo_goal: CEOGoal


class GetCompanyDTO(_DTO):
    user_id: UUID
    company_id: UUID


class UpdateCompanyDTO(_DTO):
    user_id: UUID
    company_id: UUID
    inn: CompanyINN | None = None
    sales_model: SalesModel | None = None
    primary_sales_channel: PrimarySalesChannel | None = None
    tax_regime: TaxRegime | None = None
    key_vulnerability: KeyVulnerability | None = None
    seasonality: Seasonality | None = None
    ceo_goal: CEOGoal | None = None


class GetCompanyDataDTO(_DTO):
    inn: CompanyINN


class EconomicSectorDTO(_DTO):
    classOkved: int
    name: str
    globalSector: EconomicsSectors


class CompanyInfoDTO(_DTO):
    ogrn: str
    name: str
    full_name: str
    registered_at: date | None = None
    city: str | None = None
    economicSectorCompany: list[EconomicSectorDTO]
    primaryEconomicSectorCompany: EconomicSectorDTO
    employee_count: int | None = None


class FinancialInfoDTO(_DTO):
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


class CompanyDTO(_DTO):
    inn: int
    salesModel: SalesModel
    primarySalesChannel: PrimarySalesChannel
    taxRegime: TaxRegime
    keyVulnerability: KeyVulnerability
    seasonality: Seasonality
    CEOGoal: CEOGoal
    infoCompany: CompanyInfoDTO
    financials: FinancialInfoDTO


class CompanyDataDTO(_DTO):
    inn: int
    infoCompany: CompanyInfoDTO
    financials: FinancialInfoDTO | None


class StoredCompanyDTO(_DTO):
    id: UUID
    company: CompanyDTO
