from uuid import UUID
from datetime import date

from pydantic import BaseModel, ConfigDict


class RegisteredUserResponse(BaseModel):
    user_id: UUID
    message: str = "Пользователь создан"


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int
    refresh_expires_in: int
    scope: str


class CurrentUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: str
    username: str | None
    email: str | None
    first_name: str | None
    last_name: str | None


class UserProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    last_name: str
    first_name: str
    patronymic: str
    phone_number: str
    birthday: date
