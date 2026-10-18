import asyncio
from contextlib import asynccontextmanager, suppress

from src.modules.companies.infrastructure.outbox.dispatcher import OutboxDispatcher


@asynccontextmanager
async def outbox_lifespan(session_factory, publishers, settings):
    dispatcher = OutboxDispatcher(
        session_factory, publishers, retry_seconds=settings.outbox_retry_seconds,
        max_retry_seconds=settings.outbox_max_retry_seconds,
        publish_timeout=settings.rabbitmq_publish_timeout_seconds,
    )
    task = asyncio.create_task(dispatcher.run(
        poll_interval=settings.outbox_poll_interval_seconds, batch_size=settings.outbox_batch_size,
    ), name="company-events-outbox")
    try:
        yield dispatcher
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
