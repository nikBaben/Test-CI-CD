"""Обычные тесты приложения изолированы от сетевых ресурсов брокера.

Тесты rabbitmq_integration используют настоящие lifespan и RabbitMQ.
"""
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest

import src.modules.companies.infrastructure.bootstrap as companies_bootstrap
from src.modules.companies.infrastructure.broker.resources import Publishers
from src.shared.rabbitmq.contracts import EventPublisher


@pytest.fixture(autouse=True)
def isolate_broker_resources(request, monkeypatch):
    if request.node.get_closest_marker("rabbitmq_integration"):
        return

    @asynccontextmanager
    async def messaging(*args, **kwargs):
        yield Publishers(companies=AsyncMock(spec=EventPublisher))

    @asynccontextmanager
    async def outbox(*args, **kwargs):
        yield None

    monkeypatch.setattr(companies_bootstrap, "messaging_lifespan", messaging)
    monkeypatch.setattr(companies_bootstrap, "outbox_lifespan", outbox)
