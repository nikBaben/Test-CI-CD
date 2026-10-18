import asyncio
import os
import secrets
from datetime import date
from typing import Annotated
from uuid import uuid4

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession

from src.main import create_app
from src.modules.companies.infrastructure.database.outbox_models import OutboxEventORM
from src.modules.companies.infrastructure.database.outbox_repository import SQLAlchemyCompanyOutboxRepository
from src.modules.companies.application.dto import CreateCompanyDTO, GetCompanyDTO
from src.modules.companies.application.mappers import company_to_dto
from src.modules.companies.application.exceptions import CompanyAlreadyExistsError, CompanyStorageError, StoredCompanyNotFoundError
from src.modules.companies.application.use_cases.create_company_use_case import CreateCompanyUseCase
from src.modules.companies.application.use_cases.get_company_use_case import GetCompanyUseCase
from src.modules.companies.infrastructure.database.models import CompanyEconomicSectorORM, CompanyFinanceORM, CompanyORM
from src.modules.companies.infrastructure.database.unit_of_work import SQLAlchemyCompanyUnitOfWork
from src.modules.companies.infrastructure.database.repositories import SQLAlchemyCompanyRepository
from src.modules.companies.infrastructure.deps import get_company_info_provider, get_company_uow
from src.modules.users.domain.auth import CurrentUser
from src.modules.users.infrastructure.database.models import UserORM
from src.modules.users.infrastructure.deps import get_current_user
from src.shared.config import DatabaseSettings, ServiceSettings
from src.shared.database.session import create_database, get_session
from tests.test_companies_business import BUSINESS, domain_company


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="Нужна отдельная PostgreSQL test DB")
@pytest.mark.parametrize("inn", [7816435129, 500100732259])
@pytest.mark.parametrize("missing_optional_info", [False, True])
def test_company_roundtrip_ownership_uniqueness_and_atomic_rollback(inn, missing_optional_info):
    url = os.environ["TEST_DATABASE_URL"]
    assert (make_url(url).database or "").endswith("_test")

    async def scenario():
        engine, factory = create_database(DatabaseSettings(_env_file=None, db_url=url))
        owner, other_owner = uuid4(), uuid4()
        expected = domain_company(inn)
        if missing_optional_info:
            expected.infoCompany.registered_at = None
            expected.infoCompany.city = None
            expected.infoCompany.employee_count = None
            expected.infoCompany.economicSectorCompany = []
        business = dict(BUSINESS, inn=inn)
        class Provider:
            def __init__(self):
                self.calls = 0
            async def get_info_company(self, inn):
                assert type(inn) is int
                self.calls += 1
                return expected.infoCompany
            async def get_financial_info_company(self, inn):
                assert type(inn) is int
                self.calls += 1
                return expected.financials
        provider = Provider()
        try:
            async with factory() as session:
                for user_id in (owner, other_owner):
                    session.add(UserORM(id=user_id, first_name="Иван", last_name="Тестовый", patronymic="Иванович",
                                        phone_number="79" + "".join(secrets.choice("0123456789") for _ in range(9)),
                                        birthday=date(1995, 5, 20)))
                await session.commit()
            async with factory() as session:
                result = await CreateCompanyUseCase(provider, SQLAlchemyCompanyRepository(session), SQLAlchemyCompanyUnitOfWork(session), SQLAlchemyCompanyOutboxRepository(session)).execute(CreateCompanyDTO(**business, user_id=owner))
                assert result.company == company_to_dto(expected) and provider.calls == 2
            async with factory() as session:
                repository = SQLAlchemyCompanyRepository(session)
                assert (await GetCompanyUseCase(repository).execute(GetCompanyDTO(user_id=owner, company_id=result.id))).company == company_to_dto(expected)
                with pytest.raises(StoredCompanyNotFoundError):
                    await GetCompanyUseCase(repository).execute(GetCompanyDTO(user_id=other_owner, company_id=result.id))
                row = await session.get(CompanyORM, result.id)
                assert row.user_id == owner and row.inn == inn and type(row.inn) is int
                assert row.ogrn == expected.infoCompany.ogrn
                assert row.name == expected.infoCompany.name
                assert row.full_name == expected.infoCompany.full_name
                assert row.registered_at == expected.infoCompany.registered_at
                assert row.city == expected.infoCompany.city
                assert row.employee_count == expected.infoCompany.employee_count
                assert row.primary_okved_class == expected.infoCompany.primaryEconomicSectorCompany.classOkved
                assert row.primary_okved_name == expected.infoCompany.primaryEconomicSectorCompany.name
                assert row.global_sector == expected.infoCompany.primaryEconomicSectorCompany.globalSector.value
                assert "info" not in CompanyORM.__table__.columns
                sectors = (await session.scalars(
                    select(CompanyEconomicSectorORM).where(CompanyEconomicSectorORM.company_id == result.id)
                    .order_by(CompanyEconomicSectorORM.position)
                )).all()
                assert [(s.position, s.class_okved, s.name, s.global_sector) for s in sectors] == [
                    (position, s.classOkved, s.name, s.globalSector.value) for position, s in enumerate(expected.infoCompany.economicSectorCompany)
                ]
                finance = await session.get(CompanyFinanceORM, (result.id, 2025))
                assert finance.revenue == expected.financials.revenue
                assert finance.cac is None
            async with factory() as session:
                with pytest.raises(CompanyAlreadyExistsError):
                    await CreateCompanyUseCase(provider, SQLAlchemyCompanyRepository(session), SQLAlchemyCompanyUnitOfWork(session), SQLAlchemyCompanyOutboxRepository(session)).execute(CreateCompanyDTO(**business, user_id=owner))
                assert provider.calls == 2
            async with factory() as session:
                other = await CreateCompanyUseCase(provider, SQLAlchemyCompanyRepository(session), SQLAlchemyCompanyUnitOfWork(session), SQLAlchemyCompanyOutboxRepository(session)).execute(CreateCompanyDTO(**business, user_id=other_owner))
                assert other.id != result.id
            async with factory() as session:
                uow = SQLAlchemyCompanyUnitOfWork(session)
                with pytest.raises(CompanyAlreadyExistsError):
                    await SQLAlchemyCompanyRepository(session).add(uuid4(), owner, expected)
                await uow.rollback()
            # Ошибка записи дочерней отчётности не оставляет даже родительскую строку.
            broken_id = uuid4()
            broken = expected.model_copy(deep=True)
            broken.inn = 7707049388
            broken.financials.year = 1800
            async with factory() as session:
                uow = SQLAlchemyCompanyUnitOfWork(session)
                with pytest.raises(CompanyStorageError):
                    await SQLAlchemyCompanyRepository(session).add(broken_id, owner, broken)
                await uow.rollback()
            async with factory() as session:
                assert await session.get(CompanyORM, broken_id) is None
                assert await session.scalar(select(CompanyFinanceORM).where(CompanyFinanceORM.company_id == broken_id)) is None
                assert await session.scalar(select(CompanyEconomicSectorORM).where(CompanyEconomicSectorORM.company_id == broken_id)) is None
            async with factory() as session:
                await session.execute(delete(CompanyORM).where(CompanyORM.id == other.id))
                await session.commit()
            async with factory() as session:
                assert await session.scalar(select(CompanyFinanceORM).where(CompanyFinanceORM.company_id == other.id)) is None
                assert await session.scalar(select(CompanyEconomicSectorORM).where(CompanyEconomicSectorORM.company_id == other.id)) is None
        finally:
            async with engine.begin() as connection:
                await connection.execute(delete(OutboxEventORM).where(OutboxEventORM.payload["user_id"].astext.in_([str(owner), str(other_owner)])))
                await connection.execute(delete(CompanyORM).where(CompanyORM.user_id.in_([owner, other_owner])))
                await connection.execute(delete(UserORM).where(UserORM.id.in_([owner, other_owner])))
            await engine.dispose()
    asyncio.run(scenario())


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="Нужна отдельная PostgreSQL test DB")
def test_http_repository_and_uow_share_transaction_for_commit_and_rollback():
    url = os.environ["TEST_DATABASE_URL"]
    assert (make_url(url).database or "").endswith("_test")

    async def scenario():
        engine, factory = create_database(DatabaseSettings(_env_file=None, db_url=url))
        owner = uuid4()
        expected = domain_company()

        class Provider:
            async def get_info_company(self, inn):
                return expected.infoCompany

            async def get_financial_info_company(self, inn):
                return expected.financials

        class FailingCommitUnitOfWork(SQLAlchemyCompanyUnitOfWork):
            async def commit(self):
                raise CompanyStorageError()

        def failing_uow(session: Annotated[AsyncSession, Depends(get_session)]):
            return FailingCommitUnitOfWork(session)

        app = create_app(ServiceSettings(
            _env_file=None, db_url=url, keycloak_client_secret="test", keycloak_registration_client_secret="test",
        ))
        app.dependency_overrides[get_current_user] = lambda: CurrentUser(user_id=str(owner))
        app.dependency_overrides[get_company_info_provider] = lambda: Provider()
        try:
            async with factory() as session:
                session.add(UserORM(
                    id=owner, first_name="Иван", last_name="Тестовый", patronymic="Иванович",
                    phone_number="79" + "".join(secrets.choice("0123456789") for _ in range(9)), birthday=date(1995, 5, 20),
                ))
                await session.commit()
            with TestClient(app) as client:
                created = client.post("/companies", json=BUSINESS)
                assert created.status_code == 201
                loaded = client.get("/companies/" + created.json()["id"])
                assert loaded.status_code == 200
                assert loaded.json()["company"]["inn"] == BUSINESS["inn"]
                assert client.post("/companies", json=BUSINESS).status_code == 409
                app.dependency_overrides[get_company_uow] = failing_uow
                assert client.post("/companies", json=dict(BUSINESS, inn=500100732259)).status_code == 503
            async with factory() as session:
                assert await session.scalar(select(CompanyORM).where(
                    CompanyORM.user_id == owner, CompanyORM.inn == 500100732259,
                )) is None
        finally:
            async with engine.begin() as connection:
                await connection.execute(delete(OutboxEventORM).where(OutboxEventORM.payload["user_id"].astext == str(owner)))
                await connection.execute(delete(CompanyORM).where(CompanyORM.user_id == owner))
                await connection.execute(delete(UserORM).where(UserORM.id == owner))
            await engine.dispose()

    asyncio.run(scenario())
