"""Ограничивает и Content-Length, и реальное тело запроса до multipart-разбора."""
import re

from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

UPLOAD_PATH = re.compile(r"^/companies/[^/]+/documents/[^/]+/[^/]+/?$")


class DocumentUploadLimitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "PUT" or not UPLOAD_PATH.fullmatch(scope["path"]):
            return await self.app(scope, receive, send)
        limit = scope["app"].state.document_max_bytes + 64 * 1024  # небольшой запас для multipart-заголовков
        headers = dict(scope["headers"])
        try:
            declared_size = int(headers.get(b"content-length", b"0"))
            if declared_size < 0:
                raise ValueError()
        except ValueError:
            return await JSONResponse({"detail": "Некорректный Content-Length"}, status_code=400)(scope, receive, send)
        if declared_size > limit:
            return await JSONResponse({"detail": "Превышен допустимый размер запроса"}, status_code=413)(scope, receive, send)
        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    # Starlette закрывает временные файлы multipart при исключении из потока.
                    raise HTTPException(413, "Превышен допустимый размер запроса")
            return message

        return await self.app(scope, limited_receive, send)
