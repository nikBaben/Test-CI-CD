from src.shared.rabbitmq.connection import RabbitMQConnection
from src.shared.rabbitmq.contracts import EventPublisher
from src.shared.rabbitmq.publisher import RabbitMQPublisher
from src.modules.companies.infrastructure.broker.topology import declare_companies_topology


async def create_companies_publisher(connection: RabbitMQConnection, *, publish_timeout: float = 5) -> EventPublisher:
    """Один канал на publisher, подтверждения и исключение при отсутствии маршрута."""
    channel = await connection.create_channel(publisher_confirms=True, on_return_raises=True)
    try:
        exchange, _ = await declare_companies_topology(channel)
        return RabbitMQPublisher(exchange=exchange, mandatory=True, timeout=publish_timeout)
    except BaseException:
        await channel.close()
        raise
