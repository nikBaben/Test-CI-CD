from typing import Annotated, Any

from pydantic import BeforeValidator

from src.modules.companies.domain.enums import TaxRegime
from src.modules.companies.domain.exceptions import InvalidCompanyInnError, InvalidCompanyTaxRegimeError


def validate_inn(value: Any) -> int:
    """ИНН — int из 10 или 12 цифр с верными контрольными разрядами."""
    if type(value) is not int:
        raise InvalidCompanyInnError("ИНН должен быть целым числом (int)")
    if value <= 0 or len(str(value)) not in (10, 12):
        raise InvalidCompanyInnError("ИНН должен содержать 10 или 12 цифр")

    digits = tuple(map(int, str(value)))
    if len(digits) == 10:
        checks = ((9, (2, 4, 10, 3, 5, 9, 4, 6, 8)),)
    else:
        checks = (
            (10, (7, 2, 4, 10, 3, 5, 9, 4, 6, 8)),
            (11, (3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8)),
        )
    for position, weights in checks:
        check = sum(digit * weight for digit, weight in zip(digits, weights)) % 11 % 10
        if digits[position] != check:
            raise InvalidCompanyInnError("Неверная контрольная цифра ИНН")
    return value


CompanyINN = Annotated[int, BeforeValidator(validate_inn)]


def validate_company_tax_regime(inn: int, tax_regime: TaxRegime) -> None:
    inn_str = str(inn)
    if len(inn_str) == 10 and tax_regime \
        not in (TaxRegime.OSNO,
                TaxRegime.USN,
                TaxRegime.ESXH,
                TaxRegime.AUSN
        ):
        raise InvalidCompanyTaxRegimeError("Для ИНН из 10 цифр доступны OSNO, USN, ESXH, AUSN")

