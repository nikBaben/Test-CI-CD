from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.modules.companies.application.exceptions import (
    CompanyDataAccessError, CompanyDataError, CompanyDataUnavailableError,
    CompanyNotFoundError, FinancialStatementsNotFoundError,
    CompanyAlreadyExistsError, CompanyOwnerNotFoundError, CompanyStorageError, StoredCompanyNotFoundError,
)
from src.modules.companies.domain.exceptions import CompanyValidationError


async def company_data_error_handler(request: Request, exc: CompanyDataError) -> JSONResponse:
    status, detail = 502, "Checko вернул некорректные данные"
    if isinstance(exc, CompanyNotFoundError):
        status, detail = 404, "Компания не найдена в Checko"
    elif isinstance(exc, FinancialStatementsNotFoundError):
        status, detail = 404, "Финансовая отчётность не найдена в Checko"
    elif isinstance(exc, CompanyDataUnavailableError):
        status, detail = 503, "Данные Checko временно недоступны; проверь соединение и настройки сервиса"
    elif isinstance(exc, CompanyDataAccessError):
        status, detail = 502, "Checko отклонил запрос: проверь API-ключ и лимиты"
    elif isinstance(exc, CompanyAlreadyExistsError):
        status, detail = 409, "Компания с таким ИНН уже добавлена пользователем"
    elif isinstance(exc, CompanyOwnerNotFoundError):
        status, detail = 404, "Профиль пользователя не найден в БД приложения"
    elif isinstance(exc, StoredCompanyNotFoundError):
        status, detail = 404, "Компания не найдена"
    elif isinstance(exc, CompanyStorageError):
        status, detail = 503, "Не удалось прочитать или сохранить компанию в PostgreSQL"
    return JSONResponse(status_code=status, content={"detail": detail})


async def company_validation_error_handler(request: Request, exc: CompanyValidationError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(exc)})


def register_company_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(CompanyDataError, company_data_error_handler)
    app.add_exception_handler(CompanyValidationError, company_validation_error_handler)
