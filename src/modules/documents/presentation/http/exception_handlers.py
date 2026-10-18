from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.modules.documents.domain.exceptions import (
    DocumentCompanyNotFoundError, DocumentError, DocumentNotFoundError,
    DocumentTooLargeError, DocumentValidationError,
)


async def document_error_handler(request: Request, exc: DocumentError) -> JSONResponse:
    if isinstance(exc, DocumentCompanyNotFoundError):
        status, detail = 404, "Компания не найдена"
    elif isinstance(exc, DocumentNotFoundError):
        status, detail = 404, "Документ не найден"
    elif isinstance(exc, DocumentTooLargeError):
        status, detail = 413, "Превышен допустимый размер PDF"
    elif isinstance(exc, DocumentValidationError):
        status, detail = 422, str(exc)
    else:
        status, detail = 503, "Не удалось сохранить или получить документ; проверь PostgreSQL и MinIO"
    return JSONResponse(status_code=status, content={"detail": detail})


def register_document_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DocumentError, document_error_handler)
