from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
from typing import Any

from src.modules.companies.application.exceptions import CompanyDataFormatError, FinancialStatementsNotFoundError
from src.modules.companies.domain.entities import EconomicSectorCompany, FinancialInfoCompany, InfoCompany
from src.modules.companies.domain.enums import SECTORS
from src.modules.companies.infrastructure.checko.models.responses import CheckoActivity, CheckoCompany


def decimal_or_none(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise CompanyDataFormatError()
    try:
        result = Decimal(str(value))
    except InvalidOperation:
        raise CompanyDataFormatError() from None
    if not result.is_finite():
        raise CompanyDataFormatError()
    return result


def line(report: dict, code: str) -> Decimal | None:
    value = report.get(code)
    if isinstance(value, dict):
        value = value.get("СумОтч")
    return decimal_or_none(value)


def ratio(numerator: Decimal | None, denominator: Decimal | int | None, *, percent: bool = False) -> Decimal | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    with localcontext() as context:
        context.prec = 38
        try:
            result = numerator / Decimal(denominator)
            if percent:
                result *= 100
            return result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        except InvalidOperation:
            raise CompanyDataFormatError() from None


def positive_expense(value: Decimal | None) -> Decimal | None:
    return abs(value) if value is not None else None


def map_activity(data: CheckoActivity) -> EconomicSectorCompany:
    class_okved = int(data.code.split(".")[0])
    if not any(start <= class_okved <= end for start, end, _ in SECTORS):
        raise CompanyDataFormatError()
    return EconomicSectorCompany(classOkved=class_okved, name=data.name)


def map_company(data: CheckoCompany) -> InfoCompany:
    return InfoCompany(
        ogrn=data.ogrn, name=data.name or data.full_name, full_name=data.full_name,
        registered_at=data.registered_at, city=data.address.city if data.address else None,
        economicSectorCompany=[map_activity(activity) for activity in data.additional_activities],
        primaryEconomicSectorCompany=map_activity(data.primary_activity), employee_count=data.employee_count,
    )


def cost_of_sales(report: dict) -> Decimal | None:
    row = report.get("2120")
    simplified = any(isinstance(value, dict) and "ВПокОПП" in value for value in report.values())
    if isinstance(row, dict) and "ДопПокОП" in row:
        details = row["ДопПокОП"]
        if not isinstance(details, list):
            raise CompanyDataFormatError()
        for detail in details:
            if isinstance(detail, dict) and str(detail.get("НаимПок", "")).strip().casefold() == "себестоимость продаж":
                return positive_expense(decimal_or_none(detail.get("СумОтч")))
        if simplified or ("2100" not in report and "2200" not in report):
            return None
    # Без детализации и признаков обычного ОФР значение 2120 неоднозначно.
    if simplified or not any(code in report for code in ("2100", "2200", "2210", "2220")):
        return None
    return positive_expense(line(report, "2120"))


def map_finances(raw: dict, *, employee_count: int | None, employee_count_year: int | None) -> FinancialInfoCompany:
    years = [int(key) for key, report in raw.items() if len(key) == 4 and key.isascii() and key.isdigit()
             and isinstance(report, dict) and any(len(code) == 4 and code.isdigit() for code in report)]
    if not years:
        raise FinancialStatementsNotFoundError()
    year = max(years)
    report = raw[str(year)]
    revenue, net_profit = line(report, "2110"), line(report, "2400")
    cost = cost_of_sales(report)
    commercial = positive_expense(line(report, "2210"))
    administrative = positive_expense(line(report, "2220"))
    gross = line(report, "2100")
    if gross is None and revenue is not None and cost is not None:
        gross = revenue - cost
    operating = commercial + administrative if commercial is not None and administrative is not None else None
    payroll = positive_expense(line(report, "4122"))
    employees = employee_count if employee_count_year == year and employee_count and employee_count > 0 else None
    return FinancialInfoCompany(
        year=year, revenue=revenue, net_profit=net_profit, cost_of_sales=cost,
        gross_profit=gross, gross_profit_margin=ratio(gross, revenue, percent=True),
        commercial_expenses=commercial, administrative_expenses=administrative, operating_expenses=operating,
        net_profit_margin=ratio(net_profit, revenue, percent=True), operating_cash_flow=line(report, "4100"),
        current_ratio=ratio(line(report, "1200"), line(report, "1500")), payroll_payments=payroll,
        payroll_payment_share=ratio(payroll, revenue, percent=True), revenue_per_employee=ratio(revenue, employees),
        sales_expense_ratio=ratio(commercial, revenue, percent=True), cac=None, ltv=None,
    )
