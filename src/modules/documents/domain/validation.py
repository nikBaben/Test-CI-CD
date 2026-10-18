"""Правила отчётного года и загружаемого PDF, независимо от HTTP и S3."""
import hashlib
from dataclasses import dataclass
from typing import Annotated, BinaryIO

from pydantic import AfterValidator

from src.modules.documents.domain.exceptions import DocumentTooLargeError, DocumentValidationError


def validate_reporting_year(value: int) -> int:
    if type(value) is not int or not 1900 <= value <= 9999:
        raise DocumentValidationError("Год отчётности должен быть в диапазоне 1900–9999")
    return value


ReportingYear = Annotated[int, AfterValidator(validate_reporting_year)]


@dataclass(frozen=True)
class ValidatedPDF:
    filename: str
    size_bytes: int
    sha256: str


def validate_pdf(source: BinaryIO, filename: str, content_type: str, max_bytes: int) -> ValidatedPDF:
    # Имя — только метаданные. Оно никогда не используется как путь в хранилище.
    filename = filename.replace("\\", "/").rsplit("/", 1)[-1].strip()
    if not filename or len(filename) > 255 or any(ord(char) < 32 or ord(char) == 127 for char in filename):
        raise DocumentValidationError("Некорректное имя файла")
    if not filename.lower().endswith(".pdf") or content_type.lower().split(";", 1)[0].strip() != "application/pdf":
        raise DocumentValidationError("Загружать можно только PDF с Content-Type application/pdf")
    digest, size, tail = hashlib.sha256(), 0, b""
    source.seek(0)
    try:
        first = True
        while chunk := source.read(64 * 1024):
            if first and not chunk.startswith(b"%PDF-"):
                raise DocumentValidationError("Файл не содержит заголовок PDF")
            first = False
            size += len(chunk)
            if size > max_bytes:
                raise DocumentTooLargeError()
            digest.update(chunk)
            tail = (tail + chunk)[-1024:]
        if first or b"%%EOF" not in tail:
            raise DocumentValidationError("PDF пуст или не содержит маркер завершения")
        return ValidatedPDF(filename, size, digest.hexdigest())
    finally:
        source.seek(0)
