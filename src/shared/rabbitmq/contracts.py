from typing import Protocol

from aio_pika import DeliveryMode
from aio_pika.abc import DateType, HeadersType

from src.shared.rabbitmq.names import QueueName, RoutingKey
from src.shared.rabbitmq.schemas import Event


class EventPublisher(Protocol):
    """Общий интерфейс отправителя событий для подсказок и проверки типов."""

    async def publish(
        self,
        event: Event,
        *,
        routing_key: RoutingKey,
        delivery_mode: DeliveryMode | None = None,
        mandatory: bool | None = None,
        timeout: float | None = None,
        headers: HeadersType | None = None,
        content_type: str | None = "application/json",
        content_encoding: str | None = "utf-8",
        priority: int | None = None,
        correlation_id: str | None = None,
        reply_to: QueueName | None = None,
        expiration: DateType = None,
        message_id: str | None = None,
        timestamp: DateType = None,
        message_type: str | None = None,
        user_id: str | None = None,
        app_id: str | None = None,
    ) -> None: ...
