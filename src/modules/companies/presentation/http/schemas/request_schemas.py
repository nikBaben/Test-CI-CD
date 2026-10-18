from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, model_validator

from src.modules.companies.domain.enums import (
    SalesModel, PrimarySalesChannel, TaxRegime, KeyVulnerability, Seasonality, CEOGoal,
)
from src.modules.companies.domain.validation import CompanyINN, validate_inn

# Path-параметр приходит текстом: сначала HTTP-парсер получает int, затем домен проверяет ИНН.
CompanyPathINN = Annotated[int, AfterValidator(validate_inn)]


class CreateCompanyRequest(BaseModel):
    """Бизнес-поля вводит клиент; сведения и отчётность загружаются из Checko."""
    model_config = ConfigDict(extra="forbid")

    inn: CompanyINN
    sales_model: SalesModel
    primary_sales_channel: PrimarySalesChannel
    tax_regime: TaxRegime
    key_vulnerability: KeyVulnerability
    seasonality: Seasonality
    ceo_goal: CEOGoal


class UpdateCompanyRequest(BaseModel):
    """PATCH: пропущенное поле сохраняется, переданное поле должно иметь значение."""
    model_config = ConfigDict(extra="forbid")

    inn: CompanyINN | None = None
    sales_model: SalesModel | None = None
    primary_sales_channel: PrimarySalesChannel | None = None
    tax_regime: TaxRegime | None = None
    key_vulnerability: KeyVulnerability | None = None
    seasonality: Seasonality | None = None
    ceo_goal: CEOGoal | None = None

    @model_validator(mode="after")
    def reject_explicit_nulls(self):
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("Поля изменения компании не могут быть null; пропусти поле, чтобы сохранить его значение")
        return self
