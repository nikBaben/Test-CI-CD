from typing import Annotated

from fastapi import APIRouter, Depends

from src.modules.companies.application.dto import GetCompanyDataDTO
from src.modules.companies.application.use_cases.get_company_data_use_case import GetCompanyDataUseCase
from src.modules.companies.infrastructure.deps import get_company_data
from src.modules.users.infrastructure.deps import CurrentUserDep
from src.modules.companies.presentation.http.schemas.request_schemas import CompanyPathINN
from src.modules.companies.presentation.http.schemas.respones_schemas import CheckoCompanyResponse

router = APIRouter(prefix="/companies", tags=["companies"])


@router.get("/{inn}/checko", response_model=CheckoCompanyResponse)
async def get_checko_company(
    inn: CompanyPathINN,
    user: CurrentUserDep,
    use_case: Annotated[GetCompanyDataUseCase, Depends(get_company_data)],
):
    result = await use_case.execute(GetCompanyDataDTO(inn=inn))
    return CheckoCompanyResponse.model_validate(result)
