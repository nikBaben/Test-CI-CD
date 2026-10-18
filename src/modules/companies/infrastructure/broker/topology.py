from aio_pika import ExchangeType
from aio_pika.abc import AbstractRobustChannel, AbstractRobustExchange, AbstractRobustQueue

from src.modules.companies.infrastructure.broker.names import Exchanges, Queues, RoutingKeys
from src.shared.rabbitmq.topology import bind_queue, declare_exchange, declare_queue


async def declare_failed_topology(channel: AbstractRobustChannel) -> None:
    exchange = await declare_exchange(channel, Exchanges.FAILED, exchange_type=ExchangeType.TOPIC, durable=True)
    queue = await declare_queue(channel, Queues.FAILED, durable=True, queue_type="quorum")
    await bind_queue(queue, exchange, routing_key=RoutingKeys.ALL_FAILED)


async def declare_companies_topology(channel: AbstractRobustChannel) -> tuple[AbstractRobustExchange, AbstractRobustQueue]:
    await declare_failed_topology(channel)
    exchange = await declare_exchange(channel, Exchanges.COMPANIES, exchange_type=ExchangeType.DIRECT, durable=True)
    queue = await declare_queue(
        channel, Queues.COMPANY_CREATED, durable=True, queue_type="quorum", dead_letter_exchange=Exchanges.FAILED,
    )
    await bind_queue(queue, exchange, routing_key=RoutingKeys.COMPANY_CREATED)
    updated_queue = await declare_queue(
        channel, Queues.COMPANY_UPDATED, durable=True, queue_type="quorum", dead_letter_exchange=Exchanges.FAILED,
    )
    await bind_queue(updated_queue, exchange, routing_key=RoutingKeys.COMPANY_UPDATED)
    return exchange, queue
