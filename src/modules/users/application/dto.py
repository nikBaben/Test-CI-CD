"""Входные и выходные данные границы router ↔ use case."""
from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from src.modules.users.domain.value_objects import Birthday, PersonName, PhoneNumber


class _DTO(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RegisterDTO(_DTO):

    last_name: PersonName
    first_name: PersonName
    patronymic: PersonName
    phone_number: PhoneNumber
    birthday: Birthday
    password: SecretStr = Field(min_length=1, max_length=1024)


class RegisterResultDTO(_DTO):
    user_id: UUID


class LoginDTO(_DTO):
    phone_number: PhoneNumber
    password: SecretStr = Field(min_length=1, max_length=1024)


class RefreshDTO(_DTO):
    refresh_token: SecretStr = Field(min_length=1)


class GetUserProfileDTO(_DTO):
    user_id: UUID


class TokenDTO(_DTO):
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int
    refresh_expires_in: int
    scope: str = ""


class UserProfileDTO(_DTO):
    id: UUID
    last_name: str
    first_name: str
    patronymic: str
    phone_number: str
    birthday: date
