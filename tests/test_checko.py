import asyncio
import copy
import json
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from src.main import create_app
from src.modules.companies.application.exceptions import (
    CompanyDataAccessError, CompanyDataFormatError, CompanyDataUnavailableError,
    FinancialStatementsNotFoundError,
)
from src.modules.companies.application.use_cases.get_company_data_use_case import GetCompanyDataUseCase
from src.modules.companies.domain.entities import InfoCompany, FinancialInfoCompany
from src.modules.companies.domain.enums import EconomicsSectors
from src.modules.companies.infrastructure.checko.client import CheckoClient
from src.modules.companies.infrastructure.checko.mappers import map_finances
from src.modules.companies.infrastructure.checko.provider import CheckoCompanyProvider
from src.modules.users.domain.auth import CurrentUser
from src.modules.users.infrastructure.deps import get_current_user
from src.shared.config import ServiceSettings

FIXTURES = Path(__file__).parent / "fixtures/checko"
INN = 7816435129


def fixture(name):
    return json.loads((FIXTURES / f"{name}.json").read_text())


@pytest.fixture
def api():
    state = {"company": fixture("company"), "finances": fixture("finances"), "calls": []}
    def transport(request):
        state["calls"].append(request)
        if "error" in state:
            raise state["error"]
        if "response" in state:
            return state["response"]
        assert request.url.params["key"] == "test-checko-key"
        assert request.url.params["inn"] == str(INN)
        if request.url.path == "/v2/finances":
            assert request.url.params["extended"] == "true"
            return httpx.Response(200, json=state["finances"])
        assert request.url.path == "/v2/company"
        return httpx.Response(200, json=state["company"])
    settings = ServiceSettings(
        _env_file=None, keycloak_client_secret="test", keycloak_registration_client_secret="test",
        db_url="postgresql+asyncpg://test:test@localhost/unused_test", checko_api_key="test-checko-key",
    )
    app = create_app(settings, checko_transport=httpx.MockTransport(transport))
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(user_id=str(uuid4()))
    with TestClient(app) as client:
        yield client, state, app


def test_complete_chain_maps_real_checko_response(api):
    client, state, _ = api
    response = client.get(f"/companies/{INN}/checko")
    assert response.status_code == 200
    result = response.json()
    info, financials = result["infoCompany"], result["financials"]
    assert result["inn"] == INN
    assert info["name"] == 'ООО "БСД"'
    assert info["ogrn"] == "1089847071181"
    assert info["registered_at"] == "2008-02-20"
    assert info["city"] == "г. Санкт-Петербург"
    assert info["employee_count"] == 35
    assert info["primaryEconomicSectorCompany"]["classOkved"] == 49
    assert info["primaryEconomicSectorCompany"]["globalSector"] == EconomicsSectors.H.value
    assert [item["classOkved"] for item in info["economicSectorCompany"]] == [46, 52, 52]
    assert financials["year"] == 2025
    assert Decimal(financials["revenue"]) == Decimal("261900000")
    assert Decimal(financials["cost_of_sales"]) == Decimal("205810000")
    assert Decimal(financials["gross_profit"]) == Decimal("56090000")
    assert Decimal(financials["gross_profit_margin"]) == Decimal("21.42")
    assert Decimal(financials["net_profit"]) == Decimal("19276000")
    assert Decimal(financials["net_profit_margin"]) == Decimal("7.36")
    assert Decimal(financials["revenue_per_employee"]) == Decimal("7482857.14")
    assert financials["cac"] is None and financials["ltv"] is None
    assert financials["payroll_payments"] is None
    assert financials["current_ratio"] is None
    assert len(state["calls"]) == 2
    # Кеш ограничен одним сценарием: следующий HTTP-запрос получает свежие данные.
    assert client.get(f"/companies/{INN}/checko").status_code == 200
    assert len(state["calls"]) == 4


def test_provider_returns_existing_domain_types():
    async def scenario():
        def transport(request):
            return httpx.Response(200, json=fixture("company" if request.url.path.endswith("company") else "finances"))
        async with httpx.AsyncClient(base_url="https://api.checko.ru/v2/", transport=httpx.MockTransport(transport)) as client:
            provider = CheckoCompanyProvider(CheckoClient(client, "test"))
            assert isinstance(await provider.get_info_company(INN), InfoCompany)
            assert isinstance(await provider.get_financial_info_company(INN), FinancialInfoCompany)
    asyncio.run(scenario())


@pytest.mark.parametrize("inn", ["10", "12", "78164351290", "-7816435129", "abcdefghij",
                                  "7816435128", "500100732249", "500100732258"])
def test_bad_inn_is_rejected_before_external_request(api, inn):
    client, state, _ = api
    assert client.get(f"/companies/{inn}/checko").status_code == 422
    assert not state["calls"]


def test_authentication_required_before_checko_request(api):
    client, state, app = api
    del app.dependency_overrides[get_current_user]
    assert client.get(f"/companies/{INN}/checko").status_code == 401
    assert not state["calls"]


def test_no_reports_does_not_invent_financial_year(api):
    client, state, _ = api
    state["finances"]["data"] = {}
    response = client.get(f"/companies/{INN}/checko")
    assert response.status_code == 200
    assert response.json()["financials"] is None
    assert response.json()["infoCompany"]["name"] == 'ООО "БСД"'


def test_company_not_found(api):
    client, state, _ = api
    state["company"]["data"] = None
    assert client.get(f"/companies/{INN}/checko").status_code == 404
    assert len(state["calls"]) == 1


@pytest.mark.parametrize("status,expected", [(401, 502), (403, 502), (429, 503), (500, 503), (404, 502)])
def test_external_http_errors(api, status, expected):
    client, state, _ = api
    state["response"] = httpx.Response(status)
    assert client.get(f"/companies/{INN}/checko").status_code == expected


def test_timeout_does_not_expose_key(api):
    client, state, _ = api
    state["error"] = httpx.ReadTimeout("https://api.checko.ru?key=test-checko-key")
    response = client.get(f"/companies/{INN}/checko")
    assert response.status_code == 503
    assert "test-checko-key" not in response.text


def test_meta_error_is_not_company_not_found(api):
    client, state, _ = api
    state["response"] = httpx.Response(200, json={"meta": {"status": "error", "message": "Invalid key test-checko-key"}})
    response = client.get(f"/companies/{INN}/checko")
    assert response.status_code == 502
    assert "test-checko-key" not in response.text


@pytest.mark.parametrize("body", [[], {"meta": {}}, {"meta": {"status": "ok"}, "data": []}])
def test_invalid_envelope(api, body):
    client, state, _ = api
    state["response"] = httpx.Response(200, json=body)
    assert client.get(f"/companies/{INN}/checko").status_code == 502


@pytest.mark.parametrize("field,value", [("ИНН", "7707049388"), ("ОКВЭД", None), ("ОКВЭД", {"Код": "04.01", "Наим": "Неизвестный сектор"}), ("ДатаРег", "yesterday"), ("СЧР", True)])
def test_incompatible_company_data_is_explicit_error(api, field, value):
    client, state, _ = api
    state["company"]["data"][field] = value
    assert client.get(f"/companies/{INN}/checko").status_code == 502


def test_optional_company_fields_remain_missing(api):
    client, state, _ = api
    for name in ("ДатаРег", "ЮрАдрес", "СЧР", "СЧРГод", "НаимСокр"):
        state["company"]["data"].pop(name)
    state["company"]["data"]["ОКВЭДДоп"] = None
    response = client.get(f"/companies/{INN}/checko")
    assert response.status_code == 200
    result = response.json()
    assert result["infoCompany"]["name"] == result["infoCompany"]["full_name"]
    assert result["infoCompany"]["economicSectorCompany"] == []
    assert result["infoCompany"]["city"] is None
    assert result["financials"]["revenue_per_employee"] is None


def test_financial_company_must_match_requested_inn(api):
    client, state, _ = api
    state["finances"]["company"]["ИНН"] = "7707049388"
    assert client.get(f"/companies/{INN}/checko").status_code == 502


def finance(raw, count=35, count_year=2025):
    return map_finances(raw, employee_count=count, employee_count_year=count_year)


def test_latest_report_and_period_alignment():
    raw = fixture("finances")["data"]
    raw["2099"] = {}
    raw["2098"] = {"note": "pending"}
    result = finance(raw, count_year=2024)
    assert result.year == 2025
    assert result.revenue_per_employee is None
    assert finance(raw, count=0).revenue_per_employee is None


def test_full_report_expenses_signs_and_ratios():
    result = finance({"2025": {"2110": 1000, "2120": -600, "2100": 400, "2400": -50,
                               "2210": -100, "2220": -200, "4100": -10,
                               "1200": 150, "1500": 100, "4122": -90}}, count=10)
    assert result.cost_of_sales == 600
    assert result.gross_profit == 400
    assert result.gross_profit_margin == Decimal("40.00")
    assert result.net_profit == -50 and result.net_profit_margin == Decimal("-5.00")
    assert result.operating_expenses == 300
    assert result.operating_cash_flow == -10
    assert result.current_ratio == Decimal("1.50")
    assert result.payroll_payment_share == Decimal("9.00")
    assert result.sales_expense_ratio == Decimal("10.00")
    assert result.revenue_per_employee == Decimal("100.00")


def test_missing_values_are_not_zero_and_zero_denominator_is_safe():
    result = finance({"2025": {"2110": 0, "2400": 0, "2210": 0, "1500": 0}})
    assert result.revenue == 0 and result.net_profit == 0
    assert result.cost_of_sales is None and result.operating_expenses is None
    assert result.current_ratio is None and result.net_profit_margin is None
    assert result.sales_expense_ratio is None


def test_simplified_total_cost_is_not_mistaken_for_cost_of_sales():
    raw = fixture("finances")["data"]
    raw["2025"]["2120"].pop("ДопПокОП")
    result = finance(raw)
    assert result.cost_of_sales is None and result.gross_profit is None


def test_ambiguous_2120_without_report_format_is_not_used_as_cost():
    result = finance({"2025": {"2110": 1000, "2120": 700, "2400": 100}})
    assert result.cost_of_sales is None and result.gross_profit is None


def test_gross_profit_can_be_derived_for_recognizable_full_report():
    result = finance({"2025": {"2110": 1000, "2120": 600, "2220": 100}})
    assert result.cost_of_sales == 600 and result.gross_profit == 400
    assert result.operating_expenses is None


def test_financial_envelope_requires_company_identity(api):
    client, state, _ = api
    state["finances"].pop("company")
    assert client.get(f"/companies/{INN}/checko").status_code == 502


@pytest.mark.parametrize("amount", [True, "NaN", "Infinity", "invalid", []])
def test_invalid_amounts_are_not_silently_accepted(amount):
    with pytest.raises(CompanyDataFormatError):
        finance({"2025": {"2110": amount}})


def test_direct_port_method_has_explicit_no_reports_error():
    with pytest.raises(FinancialStatementsNotFoundError):
        finance({})
