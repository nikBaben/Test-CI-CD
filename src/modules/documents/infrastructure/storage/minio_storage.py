"""Синхронный MinIO SDK работает в потоке, не блокируя event loop FastAPI."""
import asyncio
import hashlib
from contextlib import contextmanager
from datetime import datetime
from tempfile import SpooledTemporaryFile
from typing import BinaryIO

import urllib3
from minio import Minio
from minio.error import MinioException, S3Error

from src.modules.documents.domain.exceptions import DocumentStorageError
from src.shared.config import DocumentSettings


@contextmanager
def storage_errors():
    try:
        yield
    except (MinioException, urllib3.exceptions.HTTPError, OSError, ValueError) as exc:
        raise DocumentStorageError("Хранилище PDF недоступно или вернуло повреждённый файл") from exc


class MinioDocumentStorage:
    def __init__(self, settings: DocumentSettings):
        self.bucket = settings.minio_bucket
        self.http = urllib3.PoolManager(
            timeout=urllib3.Timeout(connect=settings.minio_timeout_seconds, read=settings.minio_timeout_seconds),
            retries=urllib3.Retry(total=0), maxsize=10,
        )
        self.client = Minio(
            settings.minio_endpoint, access_key=settings.minio_access_key.get_secret_value(),
            secret_key=settings.minio_secret_key.get_secret_value(), secure=settings.minio_secure,
            region=settings.minio_region, http_client=self.http,
        )

    def close(self) -> None:
        self.http.clear()

    async def _run(self, operation, *, close_on_cancel: bool = False):
        # Дожидаемся SDK перед освобождением исходного UploadFile/соединений при отмене запроса.
        task = asyncio.create_task(asyncio.to_thread(operation))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            try:
                result = await task
            except Exception:
                pass
            else:
                if close_on_cancel:
                    result.close()
            raise

    def _ensure_bucket(self) -> None:
        if not self.client.bucket_exists(self.bucket):
            try:
                self.client.make_bucket(self.bucket)
            except S3Error as exc:
                if exc.code != "BucketAlreadyOwnedByYou":
                    raise

    async def put(self, object_key: str, source: BinaryIO, size_bytes: int) -> None:
        def upload():
            with storage_errors():
                self._ensure_bucket()
                source.seek(0)
                self.client.put_object(self.bucket, object_key, source, size_bytes, content_type="application/pdf")
        await self._run(upload)

    async def get(self, object_key: str, size_bytes: int, sha256: str) -> BinaryIO:
        def download():
            # Первые 1 MiB в памяти, остальное во временном файле; файл закрывает HTTP-слой.
            content = SpooledTemporaryFile(max_size=1024 * 1024, mode="w+b")
            response = None
            try:
                with storage_errors():
                    response = self.client.get_object(self.bucket, object_key)
                    size, digest = 0, hashlib.sha256()
                    for chunk in response.stream(64 * 1024):
                        size += len(chunk)
                        if size > size_bytes:
                            raise ValueError("Unexpected object size")
                        digest.update(chunk)
                        content.write(chunk)
                    if size != size_bytes or digest.hexdigest() != sha256:
                        raise ValueError("Object checksum mismatch")
                    content.seek(0)
                    return content
            except BaseException:
                content.close()
                raise
            finally:
                if response is not None:
                    response.close()
                    response.release_conn()
        return await self._run(download, close_on_cancel=True)

    async def delete(self, object_key: str) -> None:
        def remove():
            with storage_errors():
                self.client.remove_object(self.bucket, object_key)
        await self._run(remove)

    async def expired_objects(self, cutoff: datetime) -> list[str]:
        def collect():
            with storage_errors():
                if not self.client.bucket_exists(self.bucket):
                    return []
                return [obj.object_name for obj in self.client.list_objects(self.bucket, recursive=True)
                        if obj.last_modified is not None and obj.last_modified < cutoff]
        return await self._run(collect)
