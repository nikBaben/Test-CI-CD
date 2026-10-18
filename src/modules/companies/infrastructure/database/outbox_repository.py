from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.companies.application.events import CompanyEvent
from src.modules.companies.application.exceptions import CompanyStorageError
from src.modules.companies.infrastructure.broker.event_routes import COMPANY_EVENT_ROUTES
from src.modules.companies.infrastructure.database.outbox_models import OutboxEventORM
from src.modules.companies.infrastructure.outbox.serialization import encode


class SQLAlchemyCompanyOutboxRepository:
    """Записывает события в PostgreSQL без публикации и без commit."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, event: CompanyEvent) -> None:
        _, routing_key = COMPANY_EVENT_ROUTES[type(event).__name__]
        try:
            self.session.add(OutboxEventORM(
                event_id=event.event_id,
                publisher_name="companies",
                event_type=type(event).__name__,
                routing_key=routing_key.value,
                payload=event.model_dump(mode="json"),
                publish_options=encode({}),
            ))
            await self.session.flush()
        except SQLAlchemyError as exc:
            raise CompanyStorageError("Не удалось записать событие компании в outbox") from exc
