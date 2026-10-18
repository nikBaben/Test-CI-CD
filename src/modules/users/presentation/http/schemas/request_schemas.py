from pydantic import BaseModel, ConfigDict, Field, SecretStr

from src.modules.users.domain.value_objects import Birthday, PersonName, PhoneNumber


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phone_number: PhoneNumber
    password: SecretStr = Field(min_length=1, max_length=1024)


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    last_name: PersonName
    first_name: PersonName
    patronymic: PersonName
    phone_number: PhoneNumber
    birthday: Birthday
    password: SecretStr = Field(min_length=1, max_length=1024)


class RefreshRequest(BaseModel):
    refresh_token: SecretStr = Field(min_length=1)
