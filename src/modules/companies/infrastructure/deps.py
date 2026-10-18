from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.rabbitmq.contracts import EventPublisher
from src.modules.companies.application.ports.company_outbox_repository import CompanyOutboxRepository
from src.modules.companies.infrastructure.broker.resources import Publishers
from src.modules.companies.infrastructure.database.outbox_repository import SQLAlchemyCompanyOutboxRepository

from src.modules.companies.application.exceptions import CompanyDataUnavailableError
from src.modules.companies.application.ports.company_data_port import CompanyInfoProvider
from src.modules.companies.application.use_cases.get_company_data_use_case import GetCompanyDataUseCase
from src.modules.companies.application.use_cases.create_company_use_case import CreateCompanyUseCase
from src.modules.companies.application.use_cases.get_company_use_case import GetCompanyUseCase
from src.modules.companies.application.use_cases.update_company_use_case import UpdateCompanyUseCase
from src.modules.companies.application.ports.company_unit_of_work import CompanyUnitOfWork
from src.modules.companies.domain.repositories import CompanyRepository
from src.modules.companies.infrastructure.database.repositories import SQLAlchemyCompanyRepository
from src.modules.companies.infrastructure.database.unit_of_work import SQLAlchemyCompanyUnitOfWork
from src.shared.database.session import get_session
from src.modules.companies.infrastructure.checko.client import CheckoClient
from src.modules.companies.infrastructure.checko.provider import CheckoCompanyProvider


def get_company_info_provider(request: Request) -> CompanyInfoProvider:
    provider = get_optional_company_info_provider(request)
    if provider is None:
        raise CompanyDataUnavailableError("Не настроен CHECKO_API_KEY")
    return provider


def get_optional_company_info_provider(request: Request) -> CompanyInfoProvider | None:
    client: CheckoClient | None = request.app.state.checko_client
    if client is None:
        return None
    return CheckoCompanyProvider(client)


def get_company_data(provider: Annotated[CompanyInfoProvider, Depends(get_company_info_provider)]) -> GetCompanyDataUseCase:
    return GetCompanyDataUseCase(provider)


# FastAPI кеширует get_session в пределах запроса: репозиторий и UoW получают одну сессию.
def get_company_repository(session: Annotated[AsyncSession, Depends(get_session)]) -> CompanyRepository:
    return SQLAlchemyCompanyRepository(session)


def get_company_uow(session: Annotated[AsyncSession, Depends(get_session)]) -> CompanyUnitOfWork:
    return SQLAlchemyCompanyUnitOfWork(session)


def get_publishers(request: Request) -> Publishers:
    return request.app.state.publishers


def get_companies_publisher(publishers: Annotated[Publishers, Depends(get_publishers)]) -> EventPublisher:
    return publishers.companies


def get_company_outbox_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CompanyOutboxRepository:
    return SQLAlchemyCompanyOutboxRepository(session)


def get_create_company(
    provider: Annotated[CompanyInfoProvider, Depends(get_company_info_provider)],
    repository: Annotated[CompanyRepository, Depends(get_company_repository)],
    uow: Annotated[CompanyUnitOfWork, Depends(get_company_uow)],
    outbox_repository: Annotated[CompanyOutboxRepository, Depends(get_company_outbox_repository)],
) -> CreateCompanyUseCase:
    return CreateCompanyUseCase(provider, repository, uow, outbox_repository)


def get_company(repository: Annotated[CompanyRepository, Depends(get_company_repository)]) -> GetCompanyUseCase:
    return GetCompanyUseCase(repository)


def get_update_company(
    provider: Annotated[CompanyInfoProvider | None, Depends(get_optional_company_info_provider)],
    repository: Annotated[CompanyRepository, Depends(get_company_repository)],
    uow: Annotated[CompanyUnitOfWork, Depends(get_company_uow)],
    outbox_repository: Annotated[CompanyOutboxRepository, Depends(get_company_outbox_repository)],
) -> UpdateCompanyUseCase:
    return UpdateCompanyUseCase(provider, repository, uow, outbox_repository)
