from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    """Текущее время UTC с явно указанным часовым поясом."""
    return datetime.now(UTC)


class Event(BaseModel):
    """Базовое событие: уникальный идентификатор и время возникновения."""

    event_id: UUID = Field(default_factory=uuid4)
    occurred_at: datetime = Field(default_factory=utc_now)
