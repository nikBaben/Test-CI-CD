import asyncio
from datetime import UTC, date, datetime
import os
import secrets
from typing import Annotated
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import Depends
from sqlalchemy import delete, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession

from src.main import create_app
from src.modules.companies.infrastructure.deps import get_company_outbox_repository
from src.modules.companies.application.events import CompanyCreated, CompanyUpdated
from src.modules.companies.infrastructure.broker.names import RoutingKeys
from src.modules.companies.infrastructure.outbox.dispatcher import OutboxDispatcher
from src.modules.companies.infrastructure.database.outbox_models import OutboxEventORM
from src.modules.companies.infrastructure.database.outbox_repository import SQLAlchemyCompanyOutboxRepository
from src.modules.companies.infrastructure.broker.resources import Publishers
from src.modules.companies.application.exceptions import CompanyStorageError
from src.modules.companies.infrastructure.database.models import CompanyORM
from src.modules.companies.infrastructure.database.repositories import SQLAlchemyCompanyRepository
from src.modules.companies.infrastructure.database.unit_of_work import SQLAlchemyCompanyUnitOfWork
from src.modules.companies.infrastructure.deps import get_company_info_provider, get_company_uow
from src.modules.users.domain.auth import CurrentUser
from src.modules.users.infrastructure.database.models import UserORM
from src.modules.users.infrastructure.deps import get_current_user
from src.shared.config import ServiceSettings
from src.shared.database.session import get_session
from tests.test_companies_business import BUSINESS, domain_company

pytestmark = pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="Нужна PostgreSQL test DB")


@pytest.mark.parametrize("failure", [None, "commit", "outbox"])
def test_company_and_outbox_are_one_transaction_and_snapshot_is_complete(failure):
    url = os.environ["TEST_DATABASE_URL"]
    assert make_url(url).database.endswith("_test")
    async def scenario():
        owner = uuid4()
        app = create_app(ServiceSettings(_env_file=None, db_url=url,
                                        keycloak_client_secret="test", keycloak_registration_client_secret="test"))
        class Provider:
            async def get_info_company(self, inn):
                return domain_company(inn).infoCompany
            async def get_financial_info_company(self, inn):
                return domain_company(inn).financials
        app.dependency_overrides[get_current_user] = lambda: CurrentUser(user_id=str(owner))
        app.dependency_overrides[get_company_info_provider] = lambda: Provider()
        class FailingUow(SQLAlchemyCompanyUnitOfWork):
            async def commit(self):
                raise CompanyStorageError()
        def failing_uow(session: Annotated[AsyncSession, Depends(get_session)]):
            return FailingUow(session)
        class InvalidOutboxRepository(SQLAlchemyCompanyOutboxRepository):
            async def add(self, event):
                # Ошибка настоящего SQL flush должна откатить и компанию, и событие.
                self.session.add(OutboxEventORM(
                    event_id=uuid4(), publisher_name="x" * 65, event_type="CompanyCreated",
                    routing_key="company.created", payload={}, publish_options={},
                ))
                await super().add(event)
        def failing_outbox(session: Annotated[AsyncSession, Depends(get_session)]):
            return InvalidOutboxRepository(session)
        if failure == "commit":
            app.dependency_overrides[get_company_uow] = failing_uow
        if failure == "outbox":
            app.dependency_overrides[get_company_outbox_repository] = failing_outbox
        async with app.router.lifespan_context(app):
            factory = app.state.session_factory
            try:
                async with factory() as session:
                    session.add(UserORM(id=owner, first_name="Иван", last_name="Тестовый", patronymic="Иванович",
                                        phone_number="79" + "".join(secrets.choice("0123456789") for _ in range(9)), birthday=date(1990,1,1)))
                    await session.commit()
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                    result = await client.post("/companies", json=BUSINESS)
                    assert result.status_code == (503 if failure else 201), result.text
                    async with factory() as session:
                        company = await session.scalar(select(CompanyORM).where(CompanyORM.user_id == owner))
                        event = await session.scalar(select(OutboxEventORM).where(OutboxEventORM.payload["user_id"].astext == str(owner)))
                        if failure:
                            assert company is None and event is None
                            return
                        assert company is not None and event is not None
                        event_id = event.event_id
                        snapshot = event.payload
                        assert snapshot["company"] == result.json()["company"]
                        assert snapshot["company_id"] == result.json()["id"]
                        assert snapshot["user_id"] == str(owner) and event.published_at is None
                        assert snapshot["company"]["infoCompany"]["primaryEconomicSectorCompany"]["globalSector"]
                        assert snapshot["company"]["financials"]["revenue"]
                    assert (await client.post("/companies", json=BUSINESS)).status_code == 409
                    changed = await client.patch(f"/companies/{result.json()['id']}", json={"sales_model":"B2C"})
                    assert changed.status_code == 200
                    async with factory() as session:
                        assert (await session.get(OutboxEventORM, event_id)).payload == snapshot
                        rows = (await session.scalars(select(OutboxEventORM).where(OutboxEventORM.payload["user_id"].astext == str(owner)))).all()
                        assert len(rows) == 2
                        update = next(row for row in rows if row.event_type == "CompanyUpdated")
                        assert update.payload["company"] == changed.json()["company"]
                        assert update.routing_key == "company.updated"

                publisher = AsyncMock()
                publisher.publish.side_effect = ConnectionError("amqp://secret:password@unavailable")
                dispatcher = OutboxDispatcher(factory, Publishers(companies=publisher), retry_seconds=0)
                assert await dispatcher.dispatch_one()
                async with factory() as session:
                    event = await session.get(OutboxEventORM, event_id)
                    assert event.attempts == 1 and event.published_at is None and event.last_error == "ConnectionError"
                # Новый отправитель имитирует перезапуск процесса: событие и event_id взяты из БД.
                publisher.publish.side_effect = None
                assert await OutboxDispatcher(factory, Publishers(companies=publisher)).dispatch_one()
                assert publisher.publish.await_count == 2
                first, second = [call.args[0] for call in publisher.publish.await_args_list]
                assert first.model_dump(mode="json") == second.model_dump(mode="json") == snapshot
                assert publisher.publish.await_args.kwargs["routing_key"] == RoutingKeys.COMPANY_CREATED
                async with factory() as session:
                    event = await session.get(OutboxEventORM, event_id)
                    assert event.attempts == 2 and event.published_at is not None and event.last_error is None
                assert await dispatcher.dispatch_one()
                update_message = publisher.publish.await_args.args[0]
                assert isinstance(update_message, CompanyUpdated)
                assert update_message.company.model_dump(mode="json") == changed.json()["company"]
                assert publisher.publish.await_args.kwargs["routing_key"] == RoutingKeys.COMPANY_UPDATED
                assert not await dispatcher.dispatch_one()
            finally:
                async with factory() as session:
                    await session.execute(delete(OutboxEventORM).where(OutboxEventORM.payload["user_id"].astext == str(owner)))
                    await session.execute(delete(CompanyORM).where(CompanyORM.user_id == owner))
                    await session.execute(delete(UserORM).where(UserORM.id == owner))
                    await session.commit()
    asyncio.run(scenario())


@pytest.mark.parametrize("failure", [None, "commit", "outbox"])
def test_updated_company_and_event_commit_or_rollback_together(failure):
    url = os.environ["TEST_DATABASE_URL"]
    assert make_url(url).database.endswith("_test")

    async def scenario():
        owner, company_id = uuid4(), uuid4()
        app = create_app(ServiceSettings(
            _env_file=None, db_url=url,
            keycloak_client_secret="test", keycloak_registration_client_secret="test",
        ))
        app.dependency_overrides[get_current_user] = lambda: CurrentUser(user_id=str(owner))

        class FailingUow(SQLAlchemyCompanyUnitOfWork):
            async def commit(self):
                raise CompanyStorageError()

        class FailingOutbox(SQLAlchemyCompanyOutboxRepository):
            async def add(self, event):
                await super().add(event)
                raise CompanyStorageError("Сбой после SQL flush события")

        def failing_uow(session: Annotated[AsyncSession, Depends(get_session)]):
            return FailingUow(session)

        def failing_outbox(session: Annotated[AsyncSession, Depends(get_session)]):
            return FailingOutbox(session)

        if failure == "commit":
            app.dependency_overrides[get_company_uow] = failing_uow
        if failure == "outbox":
            app.dependency_overrides[get_company_outbox_repository] = failing_outbox

        async with app.router.lifespan_context(app):
            factory = app.state.session_factory
            try:
                async with factory() as session:
                    session.add(UserORM(
                        id=owner, first_name="Иван", last_name="Тестовый", patronymic="Иванович",
                        phone_number="79" + "".join(secrets.choice("0123456789") for _ in range(9)),
                        birthday=date(1990, 1, 1),
                    ))
                    await session.flush()
                    await SQLAlchemyCompanyRepository(session).add(company_id, owner, domain_company())
                    await session.commit()
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                    response = await client.patch(f"/companies/{company_id}", json={"sales_model": "B2C"})
                    assert response.status_code == (503 if failure else 200), response.text
                    if not failure:
                        # Повтор тех же значений не создаёт ещё одно событие.
                        assert (await client.patch(f"/companies/{company_id}", json={"sales_model": "B2C"})).status_code == 200
                async with factory() as session:
                    company = await session.get(CompanyORM, company_id)
                    events = (await session.scalars(select(OutboxEventORM).where(
                        OutboxEventORM.payload["user_id"].astext == str(owner),
                    ))).all()
                    assert company.sales_model == ("B2B" if failure else "B2C")
                    if failure:
                        assert not events
                    else:
                        assert len(events) == 1
                        event = events[0]
                        assert event.event_type == "CompanyUpdated" and event.routing_key == "company.updated"
                        assert event.payload["company"] == response.json()["company"]
                        assert event.payload["company_id"] == str(company_id)
                        assert event.payload["user_id"] == str(owner) and event.published_at is None
            finally:
                async with factory() as session:
                    await session.execute(delete(OutboxEventORM).where(OutboxEventORM.payload["user_id"].astext == str(owner)))
                    await session.execute(delete(CompanyORM).where(CompanyORM.user_id == owner))
                    await session.execute(delete(UserORM).where(UserORM.id == owner))
                    await session.commit()

    asyncio.run(scenario())


@pytest.mark.parametrize("event_class", [CompanyCreated, CompanyUpdated])
def test_parallel_dispatchers_skip_locked_and_cancel_rolls_back_delivery_claim(event_class):
    url = os.environ["TEST_DATABASE_URL"]
    assert make_url(url).database.endswith("_test")
    async def scenario():
        from src.shared.config import DatabaseSettings
        from src.shared.database.session import create_database
        engine, factory = create_database(DatabaseSettings(_env_file=None, db_url=url))
        message = event_class(company_id=uuid4(),user_id=uuid4(),company=domain_company())
        entered, release = asyncio.Event(), asyncio.Event()
        async def publish(*args, **kwargs):
            entered.set()
            await release.wait()
        publisher = AsyncMock()
        publisher.publish.side_effect = publish
        first = OutboxDispatcher(factory, Publishers(companies=publisher))
        second = OutboxDispatcher(factory, Publishers(companies=publisher))
        task = None
        try:
            async with factory() as session:
                await SQLAlchemyCompanyOutboxRepository(session).add(message)
                await session.commit()
            task = asyncio.create_task(first.dispatch_one())
            await asyncio.wait_for(entered.wait(),5)
            assert not await second.dispatch_one()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            async with factory() as session:
                event = await session.get(OutboxEventORM,message.event_id)
                assert event.attempts == 0 and event.published_at is None
            timed = OutboxDispatcher(factory, Publishers(companies=publisher), publish_timeout=.01, retry_seconds=0)
            assert await timed.dispatch_one()
            async with factory() as session:
                event = await session.get(OutboxEventORM,message.event_id)
                assert event.attempts == 1 and event.published_at is None and event.last_error == "TimeoutError"
            release.set()
            assert await second.dispatch_one()
            assert publisher.publish.await_count == 3
        finally:
            release.set()
            if task and not task.done():
                task.cancel()
            async with engine.begin() as connection:
                await connection.execute(delete(OutboxEventORM).where(OutboxEventORM.event_id == message.event_id))
            await engine.dispose()
    asyncio.run(scenario())
