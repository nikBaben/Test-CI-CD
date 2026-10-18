"""Общие правила полей регистрации и входа."""
import re
from datetime import date
from typing import Annotated

from pydantic import AfterValidator, BeforeValidator, StringConstraints


def normalize_phone_number(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"\+?[0-9 ()-]+", value):
        raise ValueError("Передай номер телефона строкой, например +7 (999) 123-45-67")
    phone = re.sub(r"[^0-9]", "", value)
    if len(phone) != 11:
        raise ValueError("Номер телефона должен содержать 11 цифр")
    if phone.startswith("8"):
        phone = "7" + phone[1:]
    if not phone.startswith("79"):
        raise ValueError("Номер телефона должен начинаться с +79 или 89")
    return phone


def validate_birthday(value: date) -> date:
    if value > date.today():
        raise ValueError("Дата рождения не может быть в будущем")
    return value


PersonName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
PhoneNumber = Annotated[str, BeforeValidator(normalize_phone_number)]
Birthday = Annotated[date, AfterValidator(validate_birthday)]
