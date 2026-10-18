from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response

from src.modules.users.application.dto import GetUserProfileDTO, LoginDTO, RefreshDTO, RegisterDTO
from src.modules.users.application.use_cases.login_user_use_case import LoginUserUseCase
from src.modules.users.application.use_cases.refresh_tokens_use_case import RefreshTokensUseCase
from src.modules.users.application.use_cases.register_user_use_case import RegisterUserUseCase
from src.modules.users.application.use_cases.get_user_profile_use_case import GetUserProfileUseCase
from src.modules.users.infrastructure.deps import (
    CurrentUserDep, get_login_user, get_refresh_tokens, get_register_user, get_user_profile,
)
from src.modules.users.presentation.http.schemas.request_schemas import (
    RegisterRequest,
    LoginRequest,
    RefreshRequest,
)
from src.modules.users.presentation.http.schemas.respones_schemas import (
    RegisteredUserResponse,
    TokenResponse,
    CurrentUserResponse,
    UserProfileResponse,
)

auth_router = APIRouter(prefix="/auth", tags=["auth"])
users_router = APIRouter(prefix="/users", tags=["users"])


@auth_router.post("/register", response_model=RegisteredUserResponse, status_code=201)
async def register_handler(
    payload: RegisterRequest,
    use_case: Annotated[RegisterUserUseCase, Depends(get_register_user)],
):
    dto = RegisterDTO(
        last_name=payload.last_name,
        first_name=payload.first_name,
        patronymic=payload.patronymic,
        phone_number=payload.phone_number,
        birthday=payload.birthday,
        password=payload.password,
    )
    result = await use_case.execute(dto)
    return RegisteredUserResponse(user_id=result.user_id)


@auth_router.post("/login", response_model=TokenResponse)
async def login_handler(
    payload: LoginRequest, 
    response: Response,
    use_case: Annotated[LoginUserUseCase, Depends(get_login_user)],
):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    dto = LoginDTO(phone_number=payload.phone_number, password=payload.password)
    result = await use_case.execute(dto)
    return TokenResponse.model_validate(result, from_attributes=True)


@auth_router.post("/refresh", response_model=TokenResponse)
async def refresh_handler(
    payload: RefreshRequest, response: Response,
    use_case: Annotated[RefreshTokensUseCase, Depends(get_refresh_tokens)],
):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    result = await use_case.execute(RefreshDTO(refresh_token=payload.refresh_token))
    return TokenResponse.model_validate(result, from_attributes=True)


@users_router.get("/me", response_model=CurrentUserResponse)
def me_handler(user: CurrentUserDep):
    return CurrentUserResponse.model_validate(user)


@users_router.get("/profile", response_model=UserProfileResponse)
async def profile_handler(
    user: CurrentUserDep,
    use_case: Annotated[GetUserProfileUseCase, Depends(get_user_profile)],
):
    try:
        user_id = UUID(user.user_id)
    except ValueError:
        raise HTTPException(404, "Профиль пользователя не найден") from None
    result = await use_case.execute(GetUserProfileDTO(user_id=user_id))
    return UserProfileResponse.model_validate(result)
