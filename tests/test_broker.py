import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from aio_pika import DeliveryMode, ExchangeType
from aio_pika.abc import AbstractExchange

import src.modules.companies.infrastructure.broker.bootstrap as bootstrap
from src.modules.companies.application.events import CompanyCreated
from src.modules.companies.infrastructure.broker.names import Exchanges, Queues, RoutingKeys
from src.modules.companies.infrastructure.outbox.serialization import decode, encode
from src.modules.companies.infrastructure.broker.publishers import create_companies_publisher
from src.modules.companies.infrastructure.broker.resources import Publishers
from src.shared.rabbitmq.publisher import RabbitMQPublisher
from tests.test_companies_business import domain_company


def test_amqp_options_roundtrip_preserves_types_and_header_keys():
    now = datetime.now(UTC)
    options = {"delivery_mode": DeliveryMode.PERSISTENT, "mandatory": False, "content_type": None,
               "reply_to": Queues.FAILED, "expiration": timedelta(seconds=30), "timestamp": now,
               "headers": {"raw": b"\xff\x00", "amount": Decimal("1.25"), "nested": [{"type": "queue", "value": "literal"}]}}
    restored = decode(encode(options))
    assert restored["headers"] == options["headers"]
    assert restored["reply_to"].value == Queues.FAILED.value
    assert restored["expiration"] == timedelta(seconds=30) and restored["timestamp"] == now
    assert restored["delivery_mode"] == DeliveryMode.PERSISTENT and restored["content_type"] is None


def test_publisher_factory_uses_direct_exchange_durable_queue_and_confirms():
    async def scenario():
        channel = AsyncMock()
        failed, companies = AsyncMock(spec=AbstractExchange), AsyncMock(spec=AbstractExchange)
        channel.declare_exchange.side_effect = [failed, companies]
        failed_queue, company_queue, updated_queue = AsyncMock(), AsyncMock(), AsyncMock()
        channel.declare_queue.side_effect = [failed_queue, company_queue, updated_queue]
        connection = AsyncMock()
        connection.create_channel.return_value = channel
        publisher = await create_companies_publisher(connection, publish_timeout=3)
        connection.create_channel.assert_awaited_once_with(publisher_confirms=True, on_return_raises=True)
        assert channel.declare_exchange.await_args_list[1].kwargs["type"] == ExchangeType.DIRECT
        assert channel.declare_exchange.await_args_list[1].kwargs["name"] == Exchanges.COMPANIES.value
        queue_options = channel.declare_queue.await_args_list[1].kwargs
        assert queue_options["durable"] and queue_options["arguments"]["x-queue-type"] == "quorum"
        company_queue.bind.assert_awaited_once_with(companies, routing_key="company.created", arguments=None, timeout=None, robust=True)
        updated_queue.bind.assert_awaited_once_with(companies, routing_key="company.updated", arguments=None, timeout=None, robust=True)
        updated_options = channel.declare_queue.await_args_list[2].kwargs
        assert updated_options["name"] == Queues.COMPANY_UPDATED.value
        assert updated_options["durable"] and updated_options["arguments"]["x-queue-type"] == "quorum"
        event = CompanyCreated(company_id=uuid4(), user_id=uuid4(), company=domain_company())
        await publisher.publish(event, routing_key=RoutingKeys.COMPANY_CREATED)
        message = companies.publish.await_args.args[0]
        assert message.message_id == str(event.event_id) and message.delivery_mode == DeliveryMode.PERSISTENT
        assert companies.publish.await_args.kwargs == {"routing_key": "company.created", "mandatory": True, "timeout": 3}
        assert CompanyCreated.model_validate_json(message.body).company == event.company
    asyncio.run(scenario())


def test_failed_publisher_factory_closes_its_channel():
    async def scenario():
        channel, connection = AsyncMock(), AsyncMock()
        connection.create_channel.return_value = channel
        channel.declare_exchange.side_effect = RuntimeError("declaration failed")
        with pytest.raises(RuntimeError):
            await create_companies_publisher(connection)
        channel.close.assert_awaited_once()
    asyncio.run(scenario())


@pytest.mark.parametrize("fail", [False, True])
def test_bootstrap_owns_connection_and_returns_only_created_publishers(monkeypatch, fail):
    async def scenario():
        closed = []
        class Connection:
            def __init__(self, settings):
                self.settings = settings
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                closed.append(True)
        publisher = AsyncMock()
        create = AsyncMock(return_value=publisher, side_effect=RuntimeError() if fail else None)
        monkeypatch.setattr(bootstrap, "RabbitMQConnection", Connection)
        monkeypatch.setattr(bootstrap, "create_companies_publisher", create)
        try:
            async with bootstrap.messaging_lifespan(publish_timeout=4) as resources:
                assert isinstance(resources, Publishers) and resources.companies is publisher
        except RuntimeError:
            assert fail
        assert closed == [True]
        assert create.await_args.kwargs["publish_timeout"] == 4
    asyncio.run(scenario())
