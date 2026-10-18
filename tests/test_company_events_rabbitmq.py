import asyncio
from datetime import date
import json
import os
import secrets
from uuid import uuid4

import httpx
import pytest
from aio_pika.exceptions import DeliveryError
from sqlalchemy import delete, select
from sqlalchemy.engine import make_url
from yarl import URL

from src.main import create_app
from src.modules.companies.application.events import CompanyCreated, CompanyUpdated
from src.modules.companies.infrastructure.broker.names import Exchanges, Queues, RoutingKeys
from src.modules.companies.infrastructure.database.outbox_models import OutboxEventORM
from src.modules.companies.infrastructure.database.models import CompanyORM
from src.modules.companies.infrastructure.database.repositories import SQLAlchemyCompanyRepository
from src.modules.companies.infrastructure.deps import get_company_info_provider
from src.modules.users.domain.auth import CurrentUser
from src.modules.users.infrastructure.database.models import UserORM
from src.modules.users.infrastructure.deps import get_current_user
from src.shared.config import RabbitMQSettings, ServiceSettings
from src.shared.rabbitmq.connection import RabbitMQConnection
from src.shared.rabbitmq.names import RoutingKey
from tests.test_companies_business import BUSINESS, domain_company


@pytest.mark.rabbitmq_integration
@pytest.mark.parametrize("kind", ["created", "updated"])
@pytest.mark.skipif(not (os.getenv("TEST_DATABASE_URL") and os.getenv("TEST_RABBITMQ_URL")),
                    reason="Нужны PostgreSQL test DB и RabbitMQ test vhost")
def test_real_http_outbox_direct_routing_confirmed_publish_and_retry(kind):
    db_url, rabbit_url = os.environ["TEST_DATABASE_URL"], os.environ["TEST_RABBITMQ_URL"]
    assert make_url(db_url).database.endswith("_test")
    assert URL(rabbit_url).path.rstrip("/").endswith("_test")
    event_class, queue_name, routing_key = (
        (CompanyCreated, Queues.COMPANY_CREATED, RoutingKeys.COMPANY_CREATED) if kind == "created"
        else (CompanyUpdated, Queues.COMPANY_UPDATED, RoutingKeys.COMPANY_UPDATED)
    )
    async def scenario():
        owner = uuid4()
        settings = ServiceSettings(
            _env_file=None, db_url=db_url, keycloak_client_secret="test", keycloak_registration_client_secret="test",
            rabbitmq_publish_timeout_seconds=1, outbox_poll_interval_seconds=.05,
            outbox_retry_seconds=.05, outbox_max_retry_seconds=.1,
        )
        rabbit = RabbitMQSettings(_env_file=None, url=rabbit_url, connect_timeout=3, reconnect_interval=1)
        app = create_app(settings, rabbitmq_settings=rabbit)
        class Provider:
            async def get_info_company(self, inn):
                return domain_company(inn).infoCompany
            async def get_financial_info_company(self, inn):
                return domain_company(inn).financials
        app.dependency_overrides[get_current_user] = lambda: CurrentUser(user_id=str(owner))
        app.dependency_overrides[get_company_info_provider] = lambda: Provider()
        async with app.router.lifespan_context(app), RabbitMQConnection(rabbit) as observer:
            factory = app.state.session_factory
            channel = await observer.create_channel()
            queue = await channel.get_queue(queue_name.value)
            exchange = await channel.get_exchange(Exchanges.COMPANIES.value)
            await queue.purge()
            try:
                async with factory() as session:
                    session.add(UserORM(id=owner,first_name="Иван",last_name="Тестовый",patronymic="Иванович",
                                        phone_number="79"+"".join(secrets.choice("0123456789") for _ in range(9)),birthday=date(1990,1,1)))
                    await session.flush()
                    existing_id = uuid4()
                    if kind == "updated":
                        await SQLAlchemyCompanyRepository(session).add(existing_id, owner, domain_company())
                    await session.commit()
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="http://test") as client:
                    # Отсутствие маршрута заставляет mandatory publish завершиться ошибкой.
                    await queue.unbind(exchange,routing_key=routing_key.value)
                    if kind == "created":
                        result = await client.post("/companies",json=BUSINESS)
                    else:
                        result = await client.patch(f"/companies/{existing_id}", json={"sales_model": "B2C"})
                    assert result.status_code == (201 if kind == "created" else 200),result.text
                    company_id = result.json()["id"]
                    async def failed_attempt():
                        async with factory() as session:
                            row = await session.scalar(select(OutboxEventORM).where(OutboxEventORM.payload["company_id"].astext==company_id))
                            return row if row and row.attempts else None
                    pending = None
                    for _ in range(100):
                        pending = await failed_attempt()
                        if pending:
                            break
                        await asyncio.sleep(.05)
                    assert pending is not None and pending.published_at is None and pending.last_error is not None
                    event_id = pending.event_id
                    assert await queue.get(fail=False, no_ack=True) is None
                    await queue.bind(exchange,routing_key=routing_key.value)
                    message = None
                    for _ in range(100):
                        message = await queue.get(fail=False)
                        if message:
                            break
                        await asyncio.sleep(.05)
                    assert message is not None
                    body = json.loads(message.body)
                    assert body["company"] == result.json()["company"]
                    assert body["company_id"] == company_id and body["user_id"] == str(owner)
                    assert body["event_id"] == message.message_id == str(event_id)
                    assert message.routing_key == routing_key.value and message.type == event_class.__name__
                    assert message.delivery_mode == 2
                    await message.ack()
                    delivered = None
                    for _ in range(100):
                        async with factory() as session:
                            delivered = await session.get(OutboxEventORM,event_id)
                            if delivered.published_at:
                                break
                        await asyncio.sleep(.05)
                    assert delivered.published_at is not None and delivered.attempts >= 2
                    # DIRECT требует полного совпадения routing key.
                    class WrongKey(RoutingKey):
                        VALUE=f"{routing_key.value}.extra"
                    with pytest.raises(DeliveryError):
                        await app.state.publishers.companies.publish(event_class.model_validate(body),routing_key=WrongKey.VALUE)
                    assert await queue.get(fail=False, no_ack=True) is None
            finally:
                await queue.bind(exchange,routing_key=routing_key.value)
                await queue.purge()
                async with factory() as session:
                    await session.execute(delete(OutboxEventORM).where(OutboxEventORM.payload["user_id"].astext==str(owner)))
                    await session.execute(delete(CompanyORM).where(CompanyORM.user_id==owner))
                    await session.execute(delete(UserORM).where(UserORM.id==owner))
                    await session.commit()
    asyncio.run(scenario())
