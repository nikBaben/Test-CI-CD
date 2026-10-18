from uuid import uuid4

from src.modules.companies.application.events import CompanyCreated
from src.modules.companies.application.ports.company_outbox_repository import CompanyOutboxRepository

from src.modules.companies.application.dto import CreateCompanyDTO, StoredCompanyDTO
from src.modules.companies.application.mappers import company_to_dto
from src.modules.companies.application.exceptions import CompanyAlreadyExistsError, CompanyOwnerNotFoundError
from src.modules.companies.application.ports.company_data_port import CompanyInfoProvider
from src.modules.companies.application.ports.company_unit_of_work import CompanyUnitOfWork
from src.modules.companies.domain.entities import Company
from src.modules.companies.domain.repositories import CompanyRepository
from src.modules.companies.domain.validation import validate_company_tax_regime


class CreateCompanyUseCase:
    """Сценарий создания компании."""
    def __init__(self, provider: CompanyInfoProvider, repository: CompanyRepository, uow: CompanyUnitOfWork,
                 outbox_repository: CompanyOutboxRepository) -> None:
        self.provider = provider
        self.repository = repository
        self.uow = uow
        self.outbox_repository = outbox_repository

    async def execute(self, data: CreateCompanyDTO) -> StoredCompanyDTO:
        user_id = data.user_id
        validate_company_tax_regime(data.inn, data.tax_regime)
        inn = data.inn
        
        if not await self.repository.owner_exists(user_id):
            raise CompanyOwnerNotFoundError()
        
        if await self.repository.get_by_inn(user_id, inn) is not None:
            raise CompanyAlreadyExistsError()
        
        info = await self.provider.get_info_company(inn)
        financials = await self.provider.get_financial_info_company(inn)

        company = Company.create(
            inn=inn,
            salesModel=data.sales_model,
            primarySalesChannel=data.primary_sales_channel,
            taxRegime=data.tax_regime,
            keyVulnerability=data.key_vulnerability,
            seasonality=data.seasonality,
            CEOGoal=data.ceo_goal,
            infoCompany=info,
            financials=financials,
        )
        company_id = uuid4()
        try:
            await self.repository.add(company_id, user_id, company)
            await self.outbox_repository.add(
                CompanyCreated(company_id=company_id, user_id=user_id, company=company.model_copy(deep=True)),
            )
            await self.uow.commit()
        except BaseException:
            await self.uow.rollback()
            raise
        return StoredCompanyDTO(id=company_id, company=company_to_dto(company))
