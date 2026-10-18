import asyncio
import json
import os
import secrets
from datetime import date
from decimal import Decimal
from typing import Annotated
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession

from src.main import create_app
from src.modules.companies.infrastructure.database.outbox_models import OutboxEventORM
from src.modules.companies.application.dto import UpdateCompanyDTO
from src.modules.companies.application.exceptions import CompanyAlreadyExistsError, CompanyStorageError, StoredCompanyNotFoundError
from src.modules.companies.application.use_cases.update_company_use_case import UpdateCompanyUseCase
from src.modules.companies.domain.entities import Company
from src.modules.companies.domain.enums import EconomicsSectors
from src.modules.companies.infrastructure.database.models import CompanyEconomicSectorORM, CompanyFinanceORM, CompanyORM
from src.modules.companies.infrastructure.database.repositories import SQLAlchemyCompanyRepository
from src.modules.companies.infrastructure.database.outbox_repository import SQLAlchemyCompanyOutboxRepository
from src.modules.companies.infrastructure.database.unit_of_work import SQLAlchemyCompanyUnitOfWork
from src.modules.companies.infrastructure.deps import get_company_uow
from src.modules.users.domain.auth import CurrentUser
from src.modules.users.infrastructure.database.models import UserORM
from src.modules.users.infrastructure.deps import get_current_user
from src.shared.config import DatabaseSettings, ServiceSettings
from src.shared.database.session import create_database, get_session
from tests.test_companies_business import BUSINESS, FIXTURES, domain_company
from tests.test_update_company import NEW_INFO, NEW_INN

pytestmark = pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="Нужна отдельная PostgreSQL test DB")


def new_owner(owner):
    return UserORM(id=owner, first_name="Иван", last_name="Тестовый", patronymic="Иванович",
                   phone_number="79" + "".join(secrets.choice("0123456789") for _ in range(9)), birthday=date(1995, 5, 20))


@pytest.mark.parametrize("year,empty_sectors", [(2024, False), (2025, True)])
def test_http_update_persists_refresh_and_rolls_back_all_tables(year, empty_sectors):
    url = os.environ["TEST_DATABASE_URL"]
    assert (make_url(url).database or "").endswith("_test")

    async def scenario():
        engine, factory = create_database(DatabaseSettings(_env_file=None, db_url=url))
        owner = uuid4()
        state = {"owner": owner, "calls": [], "bad_year": False}

        def transport(request):
            state["calls"].append(request)
            name = "company" if request.url.path.endswith("company") else "finances"
            body = json.loads((FIXTURES / f"{name}.json").read_text())
            inn = request.url.params["inn"]
            (body["data"] if name == "company" else body["company"])["ИНН"] = inn
            if inn == str(NEW_INN):
                if name == "company":
                    body["data"].update(NEW_INFO)
                    body["data"]["СЧРГод"] = year
                    if empty_sectors:
                        body["data"].update({"ОКВЭДДоп": [], "ЮрАдрес": None, "ДатаРег": None, "СЧР": None})
                else:
                    report_year = 1800 if state["bad_year"] else year
                    body["data"] = {str(report_year): {"2110": 1000, "2120": 600, "2220": 10, "2400": 100}}
            return httpx.Response(200, json=body)

        class FailingCommit(SQLAlchemyCompanyUnitOfWork):
            async def commit(self):
                raise CompanyStorageError()

        def failing_uow(session: Annotated[AsyncSession, Depends(get_session)]):
            return FailingCommit(session)

        app = create_app(ServiceSettings(
            _env_file=None, db_url=url, keycloak_client_secret="test", keycloak_registration_client_secret="test",
            checko_api_key="test",
        ), checko_transport=httpx.MockTransport(transport))
        app.dependency_overrides[get_current_user] = lambda: CurrentUser(user_id=str(state["owner"]))

        async def snapshot(company_id):
            async with factory() as session:
                row = await session.get(CompanyORM, company_id)
                sectors = (await session.scalars(select(CompanyEconomicSectorORM).where(
                    CompanyEconomicSectorORM.company_id == company_id).order_by(CompanyEconomicSectorORM.position))).all()
                finances = (await session.scalars(select(CompanyFinanceORM).where(
                    CompanyFinanceORM.company_id == company_id).order_by(CompanyFinanceORM.year))).all()
                values = lambda obj: {column.name: getattr(obj, column.name) for column in obj.__table__.columns}
                return values(row), [values(s) for s in sectors], [values(f) for f in finances]

        try:
            async with factory() as session:
                session.add(new_owner(owner))
                await session.commit()
            with TestClient(app) as client:
                created = client.post("/companies", json=BUSINESS)
                assert created.status_code == 201
                company_id = UUID(created.json()["id"])
                route = "/companies/" + str(company_id)
                async with factory() as session:
                    session.add(CompanyFinanceORM(company_id=company_id, year=2023, revenue=Decimal("999")))
                    await session.commit()
                original = await snapshot(company_id)
                state["calls"].clear()

                # Обычный PATCH сохраняет всю историю и работает без ключа Checko.
                checko_client = app.state.checko_client
                app.state.checko_client = None
                response = client.patch(route, json={"sales_model": "B2C"})
                assert response.status_code == 200 and not state["calls"]
                app.state.checko_client = checko_client
                before_refresh = await snapshot(company_id)
                assert before_refresh[1:] == original[1:]
                assert before_refresh[0]["sales_model"] == "B2C"
                assert before_refresh[0]["created_at"] == original[0]["created_at"]

                # Ошибка дочернего INSERT возникает после UPDATE и DELETE, но откатывает все три таблицы.
                state["bad_year"] = True
                assert client.patch(route, json={"inn": NEW_INN}).status_code == 503
                assert await snapshot(company_id) == before_refresh
                state["bad_year"] = False
                app.dependency_overrides[get_company_uow] = failing_uow
                assert client.patch(route, json={"inn": NEW_INN}).status_code == 503
                assert await snapshot(company_id) == before_refresh
                del app.dependency_overrides[get_company_uow]

                state["calls"].clear()
                response = client.patch(route, json={"inn": NEW_INN, "tax_regime": "OSNO"})
                assert response.status_code == 200 and len(state["calls"]) == 2
                assert response.json()["id"] == str(company_id)
                assert client.get(route).json()["company"]["financials"]["year"] == year
                refreshed = await snapshot(company_id)
                parent, sectors, finances = refreshed
                assert parent["user_id"] == owner and parent["inn"] == NEW_INN
                assert parent["created_at"] == original[0]["created_at"]
                assert parent["name"] == NEW_INFO["НаимСокр"] and parent["sales_model"] == "B2C"
                assert parent["primary_okved_class"] == 62 and parent["global_sector"] == EconomicsSectors.J.value
                assert [f["year"] for f in finances] == [year] and finances[0]["revenue"] == 1000
                assert [s["class_okved"] for s in sectors] == ([] if empty_sectors else [63])
                assert all(s["global_sector"] == EconomicsSectors.J.value for s in sectors)
                if empty_sectors:
                    assert parent["city"] is parent["registered_at"] is parent["employee_count"] is None

                # UUID и владелец неизменны; чужой запрос не обращается к Checko.
                state["owner"] = uuid4()
                state["calls"].clear()
                assert client.patch(route, json={"sales_model": "B2G"}).status_code == 404
                assert not state["calls"] and await snapshot(company_id) == refreshed
                state["owner"] = owner

                assert client.post("/companies", json=dict(BUSINESS, inn=500100732259)).status_code == 201
                state["calls"].clear()
                assert client.patch(route, json={"inn": 500100732259}).status_code == 409
                assert not state["calls"] and await snapshot(company_id) == refreshed

                # Уникальное ограничение защищает UPDATE и без предварительного SELECT use case.
                async with factory() as session:
                    repository = SQLAlchemyCompanyRepository(session)
                    current = await repository.get_by_id_for_update(owner, company_id)
                    duplicate = Company.create(**current.model_dump(exclude={"inn", "infoCompany", "financials"}),
                                               inn=500100732259, infoCompany=current.infoCompany, financials=current.financials)
                    with pytest.raises(CompanyAlreadyExistsError):
                        await repository.update(company_id, owner, duplicate)
                    await SQLAlchemyCompanyUnitOfWork(session).rollback()
                assert await snapshot(company_id) == refreshed
                async with factory() as session:
                    with pytest.raises(StoredCompanyNotFoundError):
                        await SQLAlchemyCompanyRepository(session).update(company_id, uuid4(), current)
        finally:
            async with engine.begin() as connection:
                await connection.execute(delete(OutboxEventORM).where(OutboxEventORM.payload["user_id"].astext == str(owner)))
                await connection.execute(delete(CompanyORM).where(CompanyORM.user_id == owner))
                await connection.execute(delete(UserORM).where(UserORM.id == owner))
            await engine.dispose()

    asyncio.run(scenario())


@pytest.mark.parametrize("read_method", ["get_by_id_for_update", "get_by_id"])
def test_update_lock_serializes_changes_without_overwriting_another_patch(read_method):
    url = os.environ["TEST_DATABASE_URL"]
    assert (make_url(url).database or "").endswith("_test")

    async def scenario():
        engine, factory = create_database(DatabaseSettings(_env_file=None, db_url=url))
        owner, company_id = uuid4(), uuid4()
        try:
            async with factory() as session:
                session.add(new_owner(owner))
                await session.commit()
                await SQLAlchemyCompanyRepository(session).add(company_id, owner, domain_company())
                await session.commit()
            async with factory() as first, factory() as second:
                first_repo, second_repo = SQLAlchemyCompanyRepository(first), SQLAlchemyCompanyRepository(second)
                first_uow, second_uow = SQLAlchemyCompanyUnitOfWork(first), SQLAlchemyCompanyUnitOfWork(second)
                cached = await second.get(CompanyORM, company_id)
                assert cached.sales_model == "B2B"
                await second.commit()
                await first_repo.get_by_id_for_update(owner, company_id)
                await second.execute(text("SET LOCAL lock_timeout = '100ms'"))
                with pytest.raises(CompanyStorageError):
                    await getattr(second_repo, read_method)(owner, company_id)
                await second_uow.rollback()
                await UpdateCompanyUseCase(None, first_repo, first_uow, SQLAlchemyCompanyOutboxRepository(first)).execute(
                    UpdateCompanyDTO(user_id=owner, company_id=company_id, sales_model="B2C"))
                result = await UpdateCompanyUseCase(None, second_repo, second_uow, SQLAlchemyCompanyOutboxRepository(second)).execute(
                    UpdateCompanyDTO(user_id=owner, company_id=company_id, tax_regime="OSNO"))
                assert result.company.salesModel.value == "B2C"
            async with factory() as session:
                saved = await SQLAlchemyCompanyRepository(session).get_by_id(owner, company_id)
                assert saved.salesModel.value == "B2C" and saved.taxRegime.value == "OSNO"
        finally:
            async with engine.begin() as connection:
                await connection.execute(delete(OutboxEventORM).where(OutboxEventORM.payload["user_id"].astext == str(owner)))
                await connection.execute(delete(CompanyORM).where(CompanyORM.user_id == owner))
                await connection.execute(delete(UserORM).where(UserORM.id == owner))
            await engine.dispose()

    asyncio.run(scenario())
