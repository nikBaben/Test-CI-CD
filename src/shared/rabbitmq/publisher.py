from aio_pika import DeliveryMode, Message
from aio_pika.abc import (
    AbstractExchange,
    AbstractMessage,
    DateType,
    HeadersType,
)

from src.shared.rabbitmq.names import QueueName, RoutingKey
from src.shared.rabbitmq.schemas import Event


class RabbitMQPublisher:
    """Отправка событий и готовых сообщений в выбранный exchange."""

    def __init__(
        self,
        exchange: AbstractExchange,
        *,
        delivery_mode: DeliveryMode = DeliveryMode.PERSISTENT,
        mandatory: bool = True,
        timeout: float | None = None,
    ) -> None:
        """Задать exchange и значения по умолчанию для публикаций."""
        self._exchange = exchange
        self._delivery_mode = delivery_mode
        self._mandatory = mandatory
        self._timeout = timeout

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
    ) -> None:
        """Преобразовать событие в JSON и отправить с указанными метаданными.

        Числовой expiration задаётся в секундах. aio-pika переводит его в
        миллисекунды AMQP. None для message_id, timestamp и message_type
        берёт значение из события; timeout=None берёт таймаут из publisher.
        content_encoding описывает тело, но не меняет кодировку UTF-8 JSON.
        """
        if not isinstance(routing_key, RoutingKey):
            raise TypeError("routing_key должен быть элементом RoutingKey")
        if reply_to is not None and not isinstance(reply_to, QueueName):
            raise TypeError("reply_to должен быть элементом QueueName")

        # Сначала выбираем значения по умолчанию, затем собираем сообщение.
        if delivery_mode is None:
            delivery_mode = self._delivery_mode
        if message_id is None:
            message_id = str(event.event_id)
        if timestamp is None:
            timestamp = event.occurred_at
        if message_type is None:
            message_type = type(event).__name__

        message = Message(
            body=event.model_dump_json().encode("utf-8"),
            headers=headers,
            content_type=content_type,
            content_encoding=content_encoding,
            delivery_mode=delivery_mode,
            priority=priority,
            correlation_id=correlation_id,
            reply_to=reply_to.value if reply_to is not None else None,
            expiration=expiration,
            message_id=message_id,
            timestamp=timestamp,
            type=message_type,
            user_id=user_id,
            app_id=app_id,
        )

        await self.publish_message(
            message,
            routing_key=routing_key,
            mandatory=mandatory,
            timeout=timeout,
        )

    async def publish_message(
        self,
        message: AbstractMessage,
        *,
        routing_key: RoutingKey,
        mandatory: bool | None = None,
        timeout: float | None = None,
    ) -> None:
        """Отправить сообщение, дождавшись завершения публикации.

        Если на канале включены подтверждения, aio-pika дождётся ответа брокера.
        Ошибки публикации передаются вызывающему коду как исключения.
        None в timeout использует таймаут, заданный при создании publisher.
        """
        if not isinstance(routing_key, RoutingKey):
            raise TypeError("routing_key должен быть элементом RoutingKey")

        if mandatory is None:
            mandatory = self._mandatory
        if timeout is None:
            timeout = self._timeout

        await self._exchange.publish(
            message,
            routing_key=routing_key.value,
            mandatory=mandatory,
            timeout=timeout,
        )
