from src.modules.companies.application.dto import GetCompanyDTO, StoredCompanyDTO
from src.modules.companies.application.mappers import company_to_dto
from src.modules.companies.application.exceptions import StoredCompanyNotFoundError
from src.modules.companies.domain.repositories import CompanyRepository


class GetCompanyUseCase:
    def __init__(self, repository: CompanyRepository):
        self.repository = repository

    async def execute(self, data: GetCompanyDTO) -> StoredCompanyDTO:
        company = await self.repository.get_by_id(data.user_id, data.company_id)
        if company is None:
            raise StoredCompanyNotFoundError()
        return StoredCompanyDTO(id=data.company_id, company=company_to_dto(company))
