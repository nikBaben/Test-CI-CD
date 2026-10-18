from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CheckoMeta(BaseModel):
    status: Literal["ok", "error"]
    message: str | None = None


class CheckoEnvelope(BaseModel):
    meta: CheckoMeta
    data: dict[str, Any] | None = None
    company: dict[str, Any] | None = None


class CheckoActivity(BaseModel):
    code: str = Field(alias="Код", pattern=r"^[0-9]{2}(?:\.[0-9]{1,2}){0,2}$")
    name: str = Field(alias="Наим", min_length=1)


class CheckoAddress(BaseModel):
    city: str | None = Field(default=None, alias="НасПункт")


class CheckoCompany(BaseModel):
    model_config = ConfigDict(extra="ignore")

    inn: str = Field(alias="ИНН")
    ogrn: str = Field(alias="ОГРН", min_length=1)
    name: str | None = Field(default=None, alias="НаимСокр")
    full_name: str = Field(alias="НаимПолн", min_length=1)
    registered_at: date | None = Field(default=None, alias="ДатаРег")
    address: CheckoAddress | None = Field(default=None, alias="ЮрАдрес")
    primary_activity: CheckoActivity = Field(alias="ОКВЭД")
    additional_activities: list[CheckoActivity] = Field(default_factory=list, alias="ОКВЭДДоп")
    employee_count: int | None = Field(default=None, alias="СЧР", ge=0)
    employee_count_year: int | None = Field(default=None, alias="СЧРГод", ge=1900)

    @field_validator("additional_activities", mode="before")
    @classmethod
    def empty_activities(cls, value):
        return [] if value is None else value

    @field_validator("employee_count", "employee_count_year", mode="before")
    @classmethod
    def optional_integer(cls, value):
        if isinstance(value, bool):
            raise ValueError("Ожидалось число, а не логическое значение")
        return None if value == "" else value
