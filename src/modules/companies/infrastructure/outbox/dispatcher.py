import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from src.modules.companies.infrastructure.broker.event_routes import COMPANY_EVENT_ROUTES
from src.modules.companies.infrastructure.database.outbox_models import OutboxEventORM
from src.modules.companies.infrastructure.outbox.serialization import decode
from src.modules.companies.infrastructure.broker.resources import Publishers

logger = logging.getLogger(__name__)


class OutboxDispatcher:
    def __init__(self, session_factory, publishers: Publishers, *, retry_seconds: float = 2, max_retry_seconds: float = 60,
                 publish_timeout: float = 5):
        self.session_factory, self.publishers = session_factory, publishers
        self.retry_seconds, self.max_retry_seconds = retry_seconds, max_retry_seconds
        self.publish_timeout = publish_timeout

    async def dispatch_one(self) -> bool:
        async with self.session_factory() as session, session.begin():
            event = await session.scalar(select(OutboxEventORM).where(
                OutboxEventORM.published_at.is_(None), OutboxEventORM.next_attempt_at <= datetime.now(UTC),
            ).order_by(OutboxEventORM.created_at, OutboxEventORM.event_id).limit(1).with_for_update(skip_locked=True))
            if event is None:
                return False
            event.attempts += 1
            try:
                if event.publisher_name != "companies" or event.event_type not in COMPANY_EVENT_ROUTES:
                    raise ValueError("Неизвестный publisher или тип события в outbox")
                event_class, routing_key = COMPANY_EVENT_ROUTES[event.event_type]
                if event.routing_key != routing_key.value:
                    raise ValueError("Routing key не соответствует типу события")
                message = event_class.model_validate(event.payload)
                if message.event_id != event.event_id:
                    raise ValueError("Идентификатор события не совпадает с записью outbox")
                # Ограничиваем также ожидание восстановления robust connection, не только AMQP confirm.
                async with asyncio.timeout(self.publish_timeout):
                    await self.publishers.companies.publish(
                        message, routing_key=routing_key, **decode(event.publish_options),
                    )
            except Exception as exc:
                delay = min(self.max_retry_seconds, self.retry_seconds * 2 ** min(event.attempts - 1, 16))
                event.next_attempt_at = datetime.now(UTC) + timedelta(seconds=delay)
                # Только имя исключения: URL брокера и учётные данные в журнал/БД не попадают.
                event.last_error = type(exc).__name__
                logger.warning("Отправка события отложена: event_id=%s, error=%s", event.event_id, event.last_error)
            else:
                event.published_at = datetime.now(UTC)
                event.last_error = None
            return True

    async def run(self, *, poll_interval: float = 1, batch_size: int = 25) -> None:
        while True:
            try:
                for _ in range(batch_size):
                    if not await self.dispatch_one():
                        break
            except Exception:
                logger.warning("Outbox временно недоступен; отправка будет повторена")
            await asyncio.sleep(poll_interval)
