"""Бизнес сущность 'компания'."""
from datetime import date
from decimal import Decimal

from pydantic import (
    BaseModel,
    model_validator,
    computed_field
)

from src.modules.companies.domain.enums import (
    SalesModel,
    PrimarySalesChannel, 
    TaxRegime, 
    KeyVulnerability, 
    Seasonality,
    CEOGoal,
    EconomicsSectors, 
    SECTORS
)
from src.modules.companies.domain.validation import CompanyINN, validate_company_tax_regime

class EconomicSectorCompany(BaseModel):
    """Экономический сектор комапнии."""
    classOkved: int
    name: str

    @computed_field
    @property
    def globalSector(self) -> EconomicsSectors:
        return self._match_globalSector_by_classOkved(self.classOkved)

    @staticmethod
    def _match_globalSector_by_classOkved(classOkved) -> EconomicsSectors:
        for start, end, sector in SECTORS:
            if start <= classOkved <= end:
                return sector
        raise ValueError("Ошибка")


class InfoCompany(BaseModel):
    """Дополнительная информация о компании, которая контролируется государством."""
    ogrn: str
    name: str
    full_name: str
    registered_at: date | None = None
    city: str | None = None
    economicSectorCompany: list[EconomicSectorCompany] 
    primaryEconomicSectorCompany: EconomicSectorCompany
    employee_count: int | None = None


class FinancialInfoCompany(BaseModel):
    """Финансовая информация о компании."""
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


class Company(BaseModel):
    """Сущность 'компания'."""
    inn: CompanyINN
    salesModel: SalesModel
    primarySalesChannel: PrimarySalesChannel
    taxRegime: TaxRegime
    keyVulnerability :KeyVulnerability
    seasonality: Seasonality
    CEOGoal: CEOGoal
    infoCompany: InfoCompany
    financials: FinancialInfoCompany


    @model_validator(mode="after")
    def validate_company(self) -> Company:
        """Проверить существующее правило налогового режима по длине ИНН."""
        validate_company_tax_regime(self.inn, self.taxRegime)
        return self

    @classmethod
    def create(
        cls,
        inn: int,
        salesModel: SalesModel,
        primarySalesChannel: PrimarySalesChannel,
        taxRegime: TaxRegime,
        keyVulnerability: KeyVulnerability, 
        seasonality: Seasonality,
        CEOGoal: CEOGoal,
        infoCompany: InfoCompany,
        financials: FinancialInfoCompany,
    ) -> Company:
        return cls(
            inn = inn,
            salesModel = salesModel,
            primarySalesChannel = primarySalesChannel,
            taxRegime = taxRegime,
            keyVulnerability = keyVulnerability, 
            seasonality = seasonality,
            CEOGoal = CEOGoal,
            infoCompany = infoCompany,
            financials = financials,
        )
