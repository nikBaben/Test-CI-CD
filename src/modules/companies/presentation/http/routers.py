from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from src.modules.companies.application.dto import CreateCompanyDTO, GetCompanyDTO, UpdateCompanyDTO
from src.modules.companies.application.use_cases.create_company_use_case import CreateCompanyUseCase
from src.modules.companies.application.use_cases.get_company_use_case import GetCompanyUseCase
from src.modules.companies.application.use_cases.update_company_use_case import UpdateCompanyUseCase
from src.modules.companies.infrastructure.deps import get_create_company, get_company, get_update_company
from src.modules.companies.presentation.http.schemas.request_schemas import CreateCompanyRequest, UpdateCompanyRequest
from src.modules.companies.presentation.http.schemas.respones_schemas import CompanyResponse
from src.modules.users.infrastructure.deps import CurrentUserDep

router = APIRouter(prefix="/companies", tags=["companies"])


def owner_id(user_id: str) -> UUID:
    try:
        return UUID(user_id)
    except ValueError:
        raise HTTPException(401, "Некорректный идентификатор пользователя", headers={"WWW-Authenticate": "Bearer"}) from None


@router.post("", response_model=CompanyResponse, status_code=201, summary="Создать и сохранить компанию")
async def create_company_http_handler(
    payload: CreateCompanyRequest,
    user: CurrentUserDep,
    use_case: Annotated[CreateCompanyUseCase, Depends(get_create_company)],
):
    dto = CreateCompanyDTO(
        user_id=owner_id(user.user_id),
        inn=payload.inn,
        sales_model=payload.sales_model,
        primary_sales_channel=payload.primary_sales_channel,
        tax_regime=payload.tax_regime,
        key_vulnerability=payload.key_vulnerability,
        seasonality=payload.seasonality,
        ceo_goal=payload.ceo_goal,
    )
    result = await use_case.execute(dto)
    return CompanyResponse.model_validate(result)


@router.patch("/{company_id}", response_model=CompanyResponse, summary="Изменить свою компанию")
async def update_company_http_handler(
    company_id: UUID,
    payload: UpdateCompanyRequest,
    user: CurrentUserDep,
    use_case: Annotated[UpdateCompanyUseCase, Depends(get_update_company)],
):
    dto = UpdateCompanyDTO(
        user_id=owner_id(user.user_id), company_id=company_id,
        **payload.model_dump(exclude_unset=True),
    )
    result = await use_case.execute(dto)
    return CompanyResponse.model_validate(result)


@router.get("/{company_id}", response_model=CompanyResponse, summary="Получить свою компанию из PostgreSQL")
async def get_company_http_handler(
    company_id: UUID,
    user: CurrentUserDep,
    use_case: Annotated[GetCompanyUseCase, Depends(get_company)],
):
    dto = GetCompanyDTO(user_id=owner_id(user.user_id), company_id=company_id)
    result = await use_case.execute(dto)
    return CompanyResponse.model_validate(result)
