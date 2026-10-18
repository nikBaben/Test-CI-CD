"""Только HTTP-протокол Checko. Доменное преобразование выполняет mapper."""
import httpx
from pydantic import ValidationError

from src.modules.companies.application.exceptions import (
    CompanyDataAccessError, CompanyDataFormatError, CompanyDataUnavailableError,
    CompanyNotFoundError, FinancialStatementsNotFoundError,
)
from src.modules.companies.infrastructure.checko.models.requests import CheckoCompanyRequest, CheckoFinancesRequest
from src.modules.companies.infrastructure.checko.models.responses import CheckoEnvelope


class CheckoClient:
    def __init__(self, http_client: httpx.AsyncClient, api_key: str) -> None:
        self.http_client = http_client
        self.api_key = api_key

    async def request(self, path: str, params: dict[str, str | int]) -> CheckoEnvelope:
        try:
            response = await self.http_client.get(path, params={**params, "key": self.api_key})
        except httpx.RequestError:
            # URL содержит ключ, поэтому исходная ошибка не передаётся наружу.
            raise CompanyDataUnavailableError() from None
        if response.status_code == 429 or response.status_code >= 500:
            raise CompanyDataUnavailableError()
        if response.status_code in (401, 403):
            raise CompanyDataAccessError()
        if response.status_code != 200:
            raise CompanyDataFormatError()
        try:
            payload = CheckoEnvelope.model_validate(response.json())
        except (ValueError, ValidationError):
            raise CompanyDataFormatError() from None
        if payload.meta.status != "ok":
            # Ошибка ключа/квоты приходит в том числе с HTTP 200.
            # Произвольный meta.error не означает отсутствие компании.
            raise CompanyDataAccessError()
        return payload

    async def company(self, inn: int) -> dict:
        response = await self.request("company", CheckoCompanyRequest(inn=inn).model_dump())
        if not response.data:
            raise CompanyNotFoundError()
        return response.data

    async def finances(self, inn: int) -> dict:
        response = await self.request("finances", CheckoFinancesRequest(inn=inn).model_dump())
        if response.company and response.company.get("ИНН") != str(inn):
            raise CompanyDataFormatError()
        if not response.data:
            raise FinancialStatementsNotFoundError()
        if not response.company or response.company.get("ИНН") != str(inn):
            raise CompanyDataFormatError()
        return response.data
