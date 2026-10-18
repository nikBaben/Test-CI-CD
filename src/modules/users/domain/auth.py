"""Значения аутентификации, независимые от HTTP-схем и DTO use case."""
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field


class TokenPair(BaseModel):
    model_config = ConfigDict(frozen=True)

    access_token: str = Field(min_length=1)
    refresh_token: str = Field(min_length=1)
    token_type: str = Field(pattern="^[Bb]earer$")
    expires_in: int = Field(gt=0)
    refresh_expires_in: int = Field(ge=0)
    scope: str = ""


@dataclass(frozen=True)
class CurrentUser:
    """Идентичность из проверенного JWT, а не локальный профиль User."""
    user_id: str
    username: str | None = None
    email: str | None = None
    first_name: str | None = None
    last_name: str | None = None
