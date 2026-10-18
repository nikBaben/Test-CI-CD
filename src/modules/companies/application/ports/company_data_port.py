from typing import Protocol

from src.modules.companies.domain.entities import InfoCompany, FinancialInfoCompany


class CompanyInfoProvider(Protocol):
    """
    Контракт провайдера для дополнительной информации 
    о компании из стороннего сервиса.
    """
    async def get_info_company(self, inn: int) -> InfoCompany:
        ...

    async def get_financial_info_company(
        self, 
        inn: int,
    ) -> FinancialInfoCompany: 
        ...
