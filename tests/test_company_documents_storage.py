"""Проверка полного пути HTTP → PostgreSQL → настоящий MinIO без запросов Checko."""
import asyncio
import os
import secrets
import threading
from datetime import date
from io import BytesIO
from typing import Annotated
from uuid import uuid4

import httpx
import pytest
from fastapi import Depends
from sqlalchemy import delete, select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.main import create_app
from src.modules.companies.infrastructure.database.models import CompanyORM
from src.modules.companies.infrastructure.database.repositories import SQLAlchemyCompanyRepository
from src.modules.documents.domain.exceptions import DocumentStorageError
from src.modules.documents.infrastructure.database.models import CompanyDocumentORM
from src.modules.documents.infrastructure.database.unit_of_work import SQLAlchemyDocumentUnitOfWork
from src.modules.documents.infrastructure.deps import get_document_storage, get_document_uow
from src.modules.documents.infrastructure.storage.cleanup import cleanup_once
from src.modules.documents.infrastructure.storage.minio_storage import MinioDocumentStorage
from src.modules.users.domain.auth import CurrentUser
from src.modules.users.infrastructure.database.models import UserORM
from src.modules.users.infrastructure.deps import get_current_user
from src.shared.config import DocumentSettings, ServiceSettings
from src.shared.database.session import get_session
from tests.test_companies_business import domain_company
from tests.test_company_documents import PDF, PDF2


@pytest.mark.skipif(not (os.getenv("TEST_DATABASE_URL") and os.getenv("TEST_MINIO_ENDPOINT")),
                    reason="Нужны отдельная PostgreSQL test DB и тестовый MinIO")
def test_real_minio_postgres_http_replacement_isolation_failures_and_cleanup():
    url = os.environ["TEST_DATABASE_URL"]
    assert (make_url(url).database or "").endswith("_test")

    async def scenario():
        owner, other, company, other_company = uuid4(), uuid4(), uuid4(), uuid4()
        bucket = "company-documents-test-" + uuid4().hex
        app = create_app(ServiceSettings(
            _env_file=None, db_url=url, keycloak_client_secret="test", keycloak_registration_client_secret="test",
            minio_endpoint=os.environ["TEST_MINIO_ENDPOINT"],
            minio_access_key=os.getenv("TEST_MINIO_ACCESS_KEY", "demo-minio"),
            minio_secret_key=os.getenv("TEST_MINIO_SECRET_KEY", "demo-minio-password"), minio_bucket=bucket,
        ))
        app.dependency_overrides[get_current_user] = lambda: CurrentUser(user_id=str(owner))
        async with app.router.lifespan_context(app):
            factory, storage = app.state.session_factory, app.state.document_storage
            try:
                async with factory() as session:
                    for user_id in (owner, other):
                        session.add(UserORM(id=user_id, first_name="Иван", last_name="Документный", patronymic="Иванович",
                                            phone_number="79" + "".join(secrets.choice("0123456789") for _ in range(9)),
                                            birthday=date(1995, 5, 20)))
                    await session.flush()
                    repo = SQLAlchemyCompanyRepository(session)
                    await repo.add(company, owner, domain_company())
                    await repo.add(other_company, other, domain_company())
                    await session.commit()
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                    base = f"/companies/{company}/documents"
                    async def upload(content=PDF, kind="balance_sheet", year=2025):
                        return await client.put(f"{base}/{kind}/{year}", files={"file": ("отчёт.pdf", content, "application/pdf")})
                    created = await upload()
                    assert created.status_code == 200, created.text
                    first = created.json()
                    async with factory() as session:
                        row = await session.get(CompanyDocumentORM, first["id"])
                        old_key = row.object_key
                        assert row.company_id == company and row.user_id == owner
                        assert row.size_bytes == len(PDF)
                    async with httpx.AsyncClient() as anonymous:
                        private = await anonymous.get(f"http://{storage.client._base_url.host}/{bucket}/{old_key}")
                        assert private.status_code == 403
                    replaced = await upload(PDF2)
                    assert replaced.status_code == 200 and replaced.json()["id"] == first["id"]
                    assert replaced.json()["created_at"] == first["created_at"]
                    response = await client.get(f"{base}/balance_sheet/2025")
                    assert response.status_code == 200 and response.content == PDF2
                    assert await asyncio.to_thread(storage.client.stat_object, bucket, (await get_key(factory, first["id"])))
                    with pytest.raises(Exception):
                        await asyncio.to_thread(storage.client.stat_object, bucket, old_key)
                    for kind in ("financial_results", "changes_in_equity", "cash_flows", "targeted_funds"):
                        assert (await upload(kind=kind)).status_code == 200
                    assert (await upload(year=2024)).status_code == 200
                    assert len((await client.get(base)).json()) == 6
                    large_pdf = b"%PDF-1.4\n" + b"0" * (1200 * 1024) + b"\n%%EOF\n"
                    assert (await upload(large_pdf, year=2022)).status_code == 200
                    assert (await client.get(f"{base}/balance_sheet/2022")).content == large_pdf
                    assert (await client.get(f"/companies/{other_company}/documents")).status_code == 404
                    app.dependency_overrides[get_current_user] = lambda: CurrentUser(user_id=str(other))
                    assert (await client.get(base)).status_code == 404
                    assert (await upload()).status_code == 404
                    assert (await client.get(f"{base}/balance_sheet/2025")).status_code == 404
                    assert (await client.get(f"/companies/{other_company}/documents")).json() == []
                    app.dependency_overrides[get_current_user] = lambda: CurrentUser(user_id=str(owner))

                    # Ошибка commit не меняет действующий файл/строку. Оставшийся объект убирается сверкой.
                    class FailingUow(SQLAlchemyDocumentUnitOfWork):
                        async def commit(self):
                            raise DocumentStorageError()
                    def failing_uow(session: Annotated[AsyncSession, Depends(get_session)]):
                        return FailingUow(session)
                    current_key = await get_key(factory, first["id"])
                    app.dependency_overrides[get_document_uow] = failing_uow
                    assert (await upload(PDF)).status_code == 503
                    del app.dependency_overrides[get_document_uow]
                    assert await get_key(factory, first["id"]) == current_key
                    assert (await client.get(f"{base}/balance_sheet/2025")).content == PDF2
                    # Чужой ключ и действующие документы очистка сохраняет; старый orphan удаляет.
                    await storage.put("external.pdf", BytesIO(PDF), len(PDF))
                    await asyncio.sleep(0.02)
                    assert await cleanup_once(storage, factory, grace_seconds=0) == 1
                    assert (await client.get(f"{base}/balance_sheet/2025")).content == PDF2
                    assert await asyncio.to_thread(storage.client.stat_object, bucket, "external.pdf")

                    # Две одновременные первые загрузки в один слот — одна строка, один текущий PDF.
                    results = await asyncio.gather(upload(PDF, year=2023), upload(PDF2, year=2023))
                    assert [r.status_code for r in results] == [200, 200]
                    assert results[0].json()["id"] == results[1].json()["id"]
                    assert (await client.get(f"{base}/balance_sheet/2023")).content in (PDF, PDF2)

                    # GET удерживает FOR SHARE до получения PDF; замена ждёт и не обрывает чтение.
                    started, release = asyncio.Event(), asyncio.Event()
                    class SlowStorage:
                        async def get(self, *args):
                            started.set()
                            await release.wait()
                            return await storage.get(*args)
                        async def put(self, *args):
                            return await storage.put(*args)
                        async def delete(self, *args):
                            return await storage.delete(*args)
                    app.dependency_overrides[get_document_storage] = lambda: SlowStorage()
                    downloading = asyncio.create_task(client.get(f"{base}/balance_sheet/2025"))
                    await asyncio.wait_for(started.wait(), 5)
                    replacing = asyncio.create_task(upload(PDF))
                    await asyncio.sleep(0.1)
                    assert not replacing.done()
                    release.set()
                    downloaded, updated = await asyncio.gather(downloading, replacing)
                    assert downloaded.content == PDF2 and updated.status_code == 200
                    del app.dependency_overrides[get_document_storage]

                    # Подмена/обрыв объекта в MinIO не возвращает испорченный PDF с кодом 200.
                    current_key = await get_key(factory, first["id"])
                    await storage.put(current_key, BytesIO(PDF2), len(PDF2))
                    assert (await client.get(f"{base}/balance_sheet/2025")).status_code == 503
                    await storage.put(current_key, BytesIO(PDF), len(PDF))
                    assert (await client.get(f"{base}/balance_sheet/2025")).content == PDF

                # Составной FK запрещает привязать документ к чужому пользователю даже напрямую через SQL.
                async with factory() as session:
                    row = await session.scalar(select(CompanyDocumentORM).where(CompanyDocumentORM.company_id == company))
                    row.user_id = other
                    with pytest.raises(IntegrityError):
                        await session.flush()
                    await session.rollback()
            finally:
                async with factory() as session:
                    await session.execute(delete(CompanyORM).where(CompanyORM.id.in_([company, other_company])))
                    await session.execute(delete(UserORM).where(UserORM.id.in_([owner, other])))
                    await session.commit()
                    assert await session.scalar(select(CompanyDocumentORM.id).where(CompanyDocumentORM.company_id == company)) is None
                if await asyncio.to_thread(storage.client.bucket_exists, bucket):
                    objects = await asyncio.to_thread(lambda: list(storage.client.list_objects(bucket, recursive=True)))
                    for obj in objects:
                        await storage.delete(obj.object_name)
                    await asyncio.to_thread(storage.client.remove_bucket, bucket)

    async def get_key(factory, document_id):
        async with factory() as session:
            return (await session.get(CompanyDocumentORM, document_id)).object_key

    asyncio.run(scenario())


def test_cancelled_storage_download_waits_for_sdk_and_closes_temporary_file():
    async def scenario():
        storage = MinioDocumentStorage(DocumentSettings(
            _env_file=None, minio_access_key="test", minio_secret_key="test-password",
        ))
        started, release = threading.Event(), threading.Event()
        content = BytesIO(PDF)
        def blocking_download():
            started.set()
            release.wait(timeout=5)
            return content
        task = asyncio.create_task(storage._run(blocking_download, close_on_cancel=True))
        try:
            assert await asyncio.to_thread(started.wait, 5)
            task.cancel()
            await asyncio.sleep(0)
            assert not task.done()
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert content.closed
        finally:
            release.set()
            storage.close()
    asyncio.run(scenario())
