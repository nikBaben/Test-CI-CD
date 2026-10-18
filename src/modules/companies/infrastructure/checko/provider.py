from pydantic import ValidationError

from src.modules.companies.application.exceptions import CompanyDataFormatError
from src.modules.companies.domain.entities import FinancialInfoCompany, InfoCompany
from src.modules.companies.infrastructure.checko.client import CheckoClient
from src.modules.companies.infrastructure.checko.mappers import map_company, map_finances
from src.modules.companies.infrastructure.checko.models.responses import CheckoCompany


class CheckoCompanyProvider:
    """Реализация CompanyInfoProvider. Один экземпляр на HTTP-запрос/сценарий."""
    def __init__(self, client: CheckoClient) -> None:
        self.client = client
        self._company: CheckoCompany | None = None

    async def _get_company(self, inn: int) -> CheckoCompany:
        if self._company is None or self._company.inn != str(inn):
            raw = await self.client.company(inn)
            try:
                company = CheckoCompany.model_validate(raw)
            except ValidationError:
                raise CompanyDataFormatError() from None
            if company.inn != str(inn):
                raise CompanyDataFormatError()
            self._company = company
        return self._company

    async def get_info_company(self, inn: int) -> InfoCompany:
        return map_company(await self._get_company(inn))

    async def get_financial_info_company(self, inn: int) -> FinancialInfoCompany:
        company = await self._get_company(inn)
        raw = await self.client.finances(inn)
        return map_finances(raw, employee_count=company.employee_count, employee_count_year=company.employee_count_year)
