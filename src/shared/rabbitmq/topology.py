from typing import Literal

from aio_pika import ExchangeType
from aio_pika.abc import (
    AbstractExchange,
    AbstractRobustChannel,
    AbstractRobustExchange,
    AbstractRobustQueue,
    HeadersType,
)

from src.shared.rabbitmq.names import ExchangeName, QueueName, RoutingKey


async def declare_exchange(
    channel: AbstractRobustChannel,
    name: ExchangeName,
    *,
    exchange_type: ExchangeType | str = ExchangeType.TOPIC,
    durable: bool = True,
    auto_delete: bool = False,
    internal: bool = False,
    passive: bool = False,
    arguments: HeadersType | None = None,
    timeout: float | None = None,
    robust: bool = True,
    alternate_exchange: ExchangeName | None = None,
    delayed_type: str | None = None,
) -> AbstractRobustExchange:
    """Объявить exchange с указанными свойствами.

    passive=True проверяет существующий exchange, robust=True восстанавливает
    его при переподключении. delayed_type требует плагин delayed-message.
    """
    if not isinstance(name, ExchangeName):
        raise TypeError("name должен быть элементом ExchangeName")
    if alternate_exchange is not None and not isinstance(
        alternate_exchange, ExchangeName
    ):
        raise TypeError("alternate_exchange должен быть элементом ExchangeName")

    # Копия защищает словарь вызывающего кода от изменений.
    exchange_arguments = dict(arguments or {})
    named_arguments: HeadersType = {
        "alternate-exchange": alternate_exchange.value
        if alternate_exchange is not None
        else None,
        "x-delayed-type": delayed_type,
    }
    for key, value in named_arguments.items():
        if value is None:
            continue
        if key in exchange_arguments:
            raise ValueError(
                f"Настройка {key} задана и отдельным параметром, и в arguments"
            )
        exchange_arguments[key] = value

    return await channel.declare_exchange(
        name=name.value,
        type=exchange_type,
        durable=durable,
        auto_delete=auto_delete,
        internal=internal,
        passive=passive,
        arguments=exchange_arguments or None,
        timeout=timeout,
        robust=robust,
    )


async def declare_queue(
    channel: AbstractRobustChannel,
    name: QueueName | None = None,
    *,
    durable: bool = True,
    exclusive: bool = False,
    passive: bool = False,
    auto_delete: bool = False,
    arguments: HeadersType | None = None,
    timeout: float | None = None,
    robust: bool = True,
    queue_type: Literal["classic", "quorum", "stream"] | None = None,
    message_ttl: int | None = None,
    expires: int | None = None,
    max_length: int | None = None,
    max_length_bytes: int | None = None,
    overflow: Literal["drop-head", "reject-publish", "reject-publish-dlx"]
    | None = None,
    dead_letter_exchange: ExchangeName | None = None,
    dead_letter_routing_key: RoutingKey | None = None,
    max_priority: int | None = None,
    single_active_consumer: bool | None = None,
    delivery_limit: int | None = None,
) -> AbstractRobustQueue:
    """Объявить очередь с указанными свойствами и расширениями.

    message_ttl и expires задаются в миллисекундах. Поддержка расширений зависит
    от типа очереди. Дополнительные расширения передаются через arguments.
    Повтор одного ключа в arguments и именованных параметрах вызывает ValueError.
    """
    # None оставляет возможность создать очередь с автоматически сгенерированным именем aio-pika.
    if name is not None and not isinstance(name, QueueName):
        raise TypeError("name должен быть элементом QueueName или None")
    if dead_letter_exchange is not None and not isinstance(
        dead_letter_exchange, ExchangeName
    ):
        raise TypeError("dead_letter_exchange должен быть элементом ExchangeName")
    if dead_letter_routing_key is not None and not isinstance(
        dead_letter_routing_key, RoutingKey
    ):
        raise TypeError("dead_letter_routing_key должен быть элементом RoutingKey")

    # Копия защищает словарь вызывающего кода от изменений.
    queue_arguments = dict(arguments or {})
    named_arguments: HeadersType = {
        "x-queue-type": queue_type,
        "x-message-ttl": message_ttl,
        "x-expires": expires,
        "x-max-length": max_length,
        "x-max-length-bytes": max_length_bytes,
        "x-overflow": overflow,
        "x-dead-letter-exchange": dead_letter_exchange.value
        if dead_letter_exchange is not None
        else None,
        "x-dead-letter-routing-key": dead_letter_routing_key.value
        if dead_letter_routing_key is not None
        else None,
        "x-max-priority": max_priority,
        "x-single-active-consumer": single_active_consumer,
        "x-delivery-limit": delivery_limit,
    }
    for key, value in named_arguments.items():
        if value is None:
            continue
        if key in queue_arguments:
            raise ValueError(
                f"Настройка {key} задана и отдельным параметром, и в arguments"
            )
        queue_arguments[key] = value

    return await channel.declare_queue(
        name=name.value if name is not None else None,
        durable=durable,
        exclusive=exclusive,
        passive=passive,
        auto_delete=auto_delete,
        arguments=queue_arguments or None,
        timeout=timeout,
        robust=robust,
    )


async def bind_queue(
    queue: AbstractRobustQueue,
    exchange: AbstractExchange | ExchangeName,
    *,
    routing_key: RoutingKey | None = None,
    arguments: HeadersType | None = None,
    timeout: float | None = None,
    robust: bool = True,
) -> None:
    """Привязать очередь к exchange по routing_key и дополнительным условиям."""
    if routing_key is not None and not isinstance(routing_key, RoutingKey):
        raise TypeError("routing_key должен быть элементом RoutingKey или None")
    if isinstance(exchange, ExchangeName):
        exchange_value: AbstractExchange | str = exchange.value
    elif not isinstance(exchange, AbstractExchange):
        raise TypeError(
            "exchange должен быть объектом exchange или элементом ExchangeName"
        )
    else:
        exchange_value = exchange

    await queue.bind(
        exchange_value,
        routing_key=routing_key.value if routing_key is not None else None,
        arguments=arguments,
        timeout=timeout,
        robust=robust,
    )


async def bind_exchange(
    destination: AbstractRobustExchange,
    source: AbstractExchange | ExchangeName,
    *,
    routing_key: RoutingKey | None = None,
    arguments: HeadersType | None = None,
    timeout: float | None = None,
    robust: bool = True,
) -> None:
    """Привязать exchange-получатель к exchange-источнику."""
    if routing_key is not None and not isinstance(routing_key, RoutingKey):
        raise TypeError("routing_key должен быть элементом RoutingKey или None")
    if isinstance(source, ExchangeName):
        source_value: AbstractExchange | str = source.value
    elif not isinstance(source, AbstractExchange):
        raise TypeError(
            "source должен быть объектом exchange или элементом ExchangeName"
        )
    else:
        source_value = source

    await destination.bind(
        source_value,
        routing_key=routing_key.value if routing_key is not None else "",
        arguments=arguments,
        timeout=timeout,
        robust=robust,
    )
