import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from src.modules.documents.infrastructure.storage.cleanup import cleanup_loop
from src.modules.documents.infrastructure.storage.minio_storage import MinioDocumentStorage
from src.modules.documents.presentation.http.exception_handlers import register_document_exception_handlers
from src.modules.documents.presentation.http.routers import router as documents_router
from src.modules.documents.presentation.http.upload_limit import DocumentUploadLimitMiddleware
from src.shared.config import DocumentSettings


def configure_documents(app: FastAPI) -> None:
    register_document_exception_handlers(app)
    app.add_middleware(DocumentUploadLimitMiddleware)
    app.include_router(documents_router)


@asynccontextmanager
async def documents_lifespan(app: FastAPI, settings: DocumentSettings):
    storage = MinioDocumentStorage(settings) if settings.minio_access_key and settings.minio_secret_key else None
    app.state.document_storage = storage
    app.state.document_max_bytes = settings.document_max_bytes
    cleanup_task = None
    try:
        if storage:
            cleanup_task = asyncio.create_task(cleanup_loop(
                storage, app.state.session_factory,
                settings.document_cleanup_interval_seconds, settings.document_cleanup_grace_seconds,
            ), name="company-documents-cleanup")
        yield
    finally:
        if cleanup_task:
            cleanup_task.cancel()
            with suppress(asyncio.CancelledError):
                await cleanup_task
        if storage:
            storage.close()
        del app.state.document_storage
        del app.state.document_max_bytes
