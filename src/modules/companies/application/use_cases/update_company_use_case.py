from pydantic import ValidationError

from src.modules.companies.application.dto import StoredCompanyDTO, UpdateCompanyDTO
from src.modules.companies.application.events import CompanyUpdated
from src.modules.companies.application.exceptions import (
    CompanyAlreadyExistsError, CompanyDataError, CompanyDataUnavailableError, StoredCompanyNotFoundError,
)
from src.modules.companies.application.mappers import company_to_dto
from src.modules.companies.application.ports.company_data_port import CompanyInfoProvider
from src.modules.companies.application.ports.company_unit_of_work import CompanyUnitOfWork
from src.modules.companies.application.ports.company_outbox_repository import CompanyOutboxRepository
from src.modules.companies.domain.entities import Company
from src.modules.companies.domain.exceptions import CompanyValidationError
from src.modules.companies.domain.repositories import CompanyRepository


class UpdateCompanyUseCase:
    """Изменить бизнес-поля своей компании, обновив сведения Checko при смене ИНН."""
    def __init__(self, provider: CompanyInfoProvider | None, repository: CompanyRepository, uow: CompanyUnitOfWork,
                 outbox_repository: CompanyOutboxRepository):
        self.provider = provider
        self.repository = repository
        self.uow = uow
        self.outbox_repository = outbox_repository

    async def execute(self, data: UpdateCompanyDTO) -> StoredCompanyDTO:
        try:
            current = await self.repository.get_by_id_for_update(data.user_id, data.company_id)
            if current is None:
                raise StoredCompanyNotFoundError()
            changes = data.model_dump(exclude_unset=True, exclude={"user_id", "company_id"})
            values = {
                "inn": changes.get("inn", current.inn),
                "salesModel": changes.get("sales_model", current.salesModel),
                "primarySalesChannel": changes.get("primary_sales_channel", current.primarySalesChannel),
                "taxRegime": changes.get("tax_regime", current.taxRegime),
                "keyVulnerability": changes.get("key_vulnerability", current.keyVulnerability),
                "seasonality": changes.get("seasonality", current.seasonality),
                "CEOGoal": changes.get("ceo_goal", current.CEOGoal),
            }
            # Проверка объединённых старых/новых полей выполняется доменной сущностью до Checko.
            updated = Company.create(**values, infoCompany=current.infoCompany, financials=current.financials)
            if updated.inn != current.inn:
                if await self.repository.get_by_inn(data.user_id, updated.inn) is not None:
                    raise CompanyAlreadyExistsError()
                if self.provider is None:
                    raise CompanyDataUnavailableError("Не настроен CHECKO_API_KEY")
                info = await self.provider.get_info_company(updated.inn)
                financials = await self.provider.get_financial_info_company(updated.inn)
                updated = Company.create(**values, infoCompany=info, financials=financials)
            if updated != current:
                await self.repository.update(data.company_id, data.user_id, updated)
                if updated.inn == current.inn:
                    await self.outbox_repository.add(CompanyUpdated(
                        company_id=data.company_id,
                        user_id=data.user_id,
                        company=updated.model_copy(deep=True),
                    ))
            await self.uow.commit()
        except ValidationError as exc:
            await self.uow.rollback()
            raise CompanyValidationError(exc.errors()[0]["msg"]) from None
        except (CompanyDataError, CompanyValidationError):
            await self.uow.rollback()
            raise
        return StoredCompanyDTO(id=data.company_id, company=company_to_dto(updated))
