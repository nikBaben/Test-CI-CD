from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

from src.modules.companies.infrastructure.broker.publishers import create_companies_publisher
from src.modules.companies.infrastructure.broker.resources import Publishers
from src.shared.config import RabbitMQSettings
from src.shared.rabbitmq.connection import RabbitMQConnection


@asynccontextmanager
async def messaging_lifespan(settings: RabbitMQSettings | None = None, *, publish_timeout: float = 5) -> AsyncIterator[Publishers]:
    """Как в эталоне: соединение → factories → resources → гарантированное закрытие."""
    async with AsyncExitStack() as cleanup:
        connection = await cleanup.enter_async_context(RabbitMQConnection(settings))
        publishers = Publishers(companies=await create_companies_publisher(connection, publish_timeout=publish_timeout))
        yield publishers
