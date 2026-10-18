"""Убирает старые объекты без метаданных: после замены, rollback или остановки процесса."""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select

from src.modules.documents.infrastructure.database.models import CompanyDocumentORM
from src.modules.documents.infrastructure.database.repositories import SQLAlchemyDocumentRepository

logger = logging.getLogger(__name__)


async def cleanup_once(storage, session_factory, *, grace_seconds: int = 3600) -> int:
    keys = await storage.expired_objects(datetime.now(timezone.utc) - timedelta(seconds=grace_seconds))
    removed = 0
    for key in keys:
        # Обслуживаем только наш формат ключей; чужие объекты бакета не трогаем.
        try:
            owner, company, filename = key.split("/")
            user_id, company_id = UUID(owner), UUID(company)
            if not filename.endswith(".pdf"):
                continue
            UUID(filename[:-4])
        except (ValueError, AttributeError):
            continue
        async with session_factory() as session:
            # Та же блокировка, что у загрузки: не удаляем ещё не закоммиченный PDF.
            await SQLAlchemyDocumentRepository(session).lock_owned_company(user_id, company_id, write=True)
            referenced = await session.scalar(select(CompanyDocumentORM.id).where(CompanyDocumentORM.object_key == key))
            if referenced is None:
                await storage.delete(key)
                removed += 1
            await session.commit()
    return removed


async def cleanup_loop(storage, session_factory, interval_seconds: int, grace_seconds: int) -> None:
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            await cleanup_once(storage, session_factory, grace_seconds=grace_seconds)
        except Exception:
            # Не выводим URL/ключи доступа и тело исключений SDK в журнал.
            logger.warning("Сверка документов MinIO с PostgreSQL отложена до следующего запуска")
