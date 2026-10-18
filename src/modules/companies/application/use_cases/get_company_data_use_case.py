from src.modules.companies.application.dto import CompanyDataDTO, GetCompanyDataDTO
from src.modules.companies.application.mappers import company_info_to_dto, financial_info_to_dto
from src.modules.companies.application.exceptions import FinancialStatementsNotFoundError
from src.modules.companies.application.ports.company_data_port import CompanyInfoProvider


class GetCompanyDataUseCase:
    def __init__(self, provider: CompanyInfoProvider):
        self.provider = provider

    async def execute(self, data: GetCompanyDataDTO) -> CompanyDataDTO:
        inn = data.inn
        info = await self.provider.get_info_company(inn)
        try:
            financials = await self.provider.get_financial_info_company(inn)
        except FinancialStatementsNotFoundError:
            financials = None
        return CompanyDataDTO(
            inn=inn, infoCompany=company_info_to_dto(info),
            financials=financial_info_to_dto(financials) if financials is not None else None,
        )
