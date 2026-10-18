from typing import Protocol

from src.modules.companies.application.events import CompanyEvent


class CompanyOutboxRepository(Protocol):
    """Сохраняет событие в транзакции компании; commit выполняет UoW."""

    async def add(self, event: CompanyEvent) -> None: ...
