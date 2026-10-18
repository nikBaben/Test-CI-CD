import asyncio
import json
from decimal import Decimal
from pathlib import Path
from uuid import uuid4
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from src.main import create_app
from src.modules.companies.infrastructure.deps import get_company_outbox_repository
from src.modules.companies.application.dto import CreateCompanyDTO
from src.modules.companies.application.exceptions import CompanyAlreadyExistsError, CompanyStorageError, StoredCompanyNotFoundError
from src.modules.companies.domain.entities import Company, FinancialInfoCompany, InfoCompany
from src.modules.companies.domain.enums import TaxRegime
from src.modules.companies.infrastructure.checko.mappers import map_company, map_finances
from src.modules.companies.infrastructure.checko.models.responses import CheckoCompany
from src.modules.companies.infrastructure.deps import get_company_repository, get_company_uow
from src.modules.users.domain.auth import CurrentUser
from src.modules.users.infrastructure.deps import get_current_user
from src.shared.config import ServiceSettings

FIXTURES = Path(__file__).parent / "fixtures/checko"
BUSINESS = {
    "inn": 7816435129, "sales_model": "B2B", "primary_sales_channel": "marketplace",
    "tax_regime": "USN", "key_vulnerability": "Import_Exchange_Rate",
    "seasonality": "Steady_Year", "ceo_goal": "Aggressive_Growth_Scaling",
}


def domain_company(inn=7816435129, tax=TaxRegime.USN):
    raw = json.loads((FIXTURES / "company.json").read_text())["data"]
    data = CheckoCompany.model_validate(raw)
    financial = json.loads((FIXTURES / "finances.json").read_text())["data"]
    return Company.create(
        inn=inn, salesModel="B2B", primarySalesChannel="marketplace", taxRegime=tax,
        keyVulnerability="Import_Exchange_Rate", seasonality="Steady_Year", CEOGoal="Aggressive_Growth_Scaling",
        infoCompany=map_company(data),
        financials=map_finances(financial, employee_count=data.employee_count, employee_count_year=data.employee_count_year),
    )


class MemoryCompanySession:
    def __init__(self, owner):
        self.owners = {owner}
        self.stored = {}
        self.pending = {}


class MemoryCompanyRepository:
    def __init__(self, session):
        self.session = session

    async def owner_exists(self, owner):
        return owner in self.session.owners

    async def get_by_id(self, owner, company_id):
        return self.session.stored.get((owner, company_id))

    async def get_by_id_for_update(self, owner, company_id):
        return await self.get_by_id(owner, company_id)

    async def get_by_inn(self, owner, inn):
        return next((company for (user_id, _), company in self.session.stored.items() if user_id == owner and company.inn == inn), None)

    async def add(self, company_id, owner, company):
        self.session.pending[(owner, company_id)] = company.model_copy(deep=True)

    async def update(self, company_id, owner, company):
        if (owner, company_id) not in self.session.stored:
            raise StoredCompanyNotFoundError()
        self.session.pending[(owner, company_id)] = company.model_copy(deep=True)


class MemoryCompanyUnitOfWork:
    def __init__(self, session):
        self.session = session
        self.committed = False
        self.rolled_back = False
        self.commit_error = None

    async def commit(self):
        if self.commit_error:
            raise self.commit_error
        self.session.stored.update(self.session.pending)
        self.session.pending.clear()
        self.committed = True

    async def rollback(self):
        self.session.pending.clear()
        self.rolled_back = True


@pytest.fixture
def api():
    owner = uuid4()
    session = MemoryCompanySession(owner)
    repository = MemoryCompanyRepository(session)
    uow = MemoryCompanyUnitOfWork(session)
    state = {"owner": owner, "calls": [], "session": session, "uow": uow}
    def transport(request):
        state["calls"].append(request)
        name = "company" if request.url.path.endswith("company") else "finances"
        body = json.loads((FIXTURES / f"{name}.json").read_text())
        # Отвечаем по запрошенному ИНН, как внешний HTTP API со строковыми полями.
        company = body["data"] if name == "company" else body["company"]
        company["ИНН"] = request.url.params["inn"]
        if "checko_info" in state and name == "company":
            body["data"].update(state["checko_info"])
        if "checko_finances" in state and name == "finances":
            body["data"] = state["checko_finances"]
        if name == "finances" and state.get("no_financials"):
            body["data"] = {}
        if state.get("upstream_error"):
            return httpx.Response(503)
        return httpx.Response(200, json=body)
    settings = ServiceSettings(_env_file=None, keycloak_client_secret="test", keycloak_registration_client_secret="test",
                               db_url="postgresql+asyncpg://test:test@localhost/unused_test", checko_api_key="test")
    app = create_app(settings, checko_transport=httpx.MockTransport(transport))
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(user_id=str(state["owner"]))
    app.dependency_overrides[get_company_uow] = lambda: uow
    app.dependency_overrides[get_company_repository] = lambda: repository
    state["outbox"] = AsyncMock()
    app.dependency_overrides[get_company_outbox_repository] = lambda: state["outbox"]
    with TestClient(app) as client:
        yield client, state, app


@pytest.mark.parametrize("inn", [7816435129, 7707083893, 500100732259])
def test_domain_checks_digit_length_instead_of_numeric_value(inn):
    company = domain_company(inn)
    assert company.inn == inn and type(company.inn) is int
    assert isinstance(company.infoCompany, InfoCompany)
    assert isinstance(company.financials, FinancialInfoCompany)


@pytest.mark.parametrize("inn", [10, 12, True, False, 123456789, 12345678901, 1234567890123, -7816435129,
                                  7816435129.0, "7816435129", "500100732259", "0123456789",
                                  None, Decimal("7816435129"), "abcdefghij", "12345 6789", "７８１６４３５１２９"])
def test_domain_rejects_invalid_inn(inn):
    with pytest.raises(ValidationError):
        domain_company(inn)


@pytest.mark.parametrize("tax", [TaxRegime.PSN, TaxRegime.NPD])
def test_ten_digit_tax_rule_is_enforced_in_domain(tax):
    with pytest.raises(ValidationError):
        domain_company(tax=tax)
    assert domain_company(500100732259, tax=tax).taxRegime == tax


def test_creates_domain_company_commits_and_reads_without_checko(api):
    client, state, _ = api
    response = client.post("/companies", json=BUSINESS)
    assert response.status_code == 201
    result = response.json()
    assert result["company"]["inn"] == 7816435129
    assert result["company"]["salesModel"] == "B2B"
    assert result["company"]["taxRegime"] == "USN"
    assert result["company"]["infoCompany"]["name"] == 'ООО "БСД"'
    assert Decimal(result["company"]["financials"]["gross_profit"]) == 56090000
    assert state["uow"].committed and len(state["calls"]) == 2
    assert client.get(f"/companies/{result['id']}").json() == result
    assert len(state["calls"]) == 2
    assert client.post("/companies", json=BUSINESS).status_code == 409
    assert len(state["calls"]) == 2


@pytest.mark.parametrize("changes", [{"inn": 10}, {"inn": "7816435128"}, {"tax_regime": "PSN"},
                                     {"tax_regime": "NPD"}, {"sales_model": "invalid"},
                                     {"user_id": str(uuid4())}, {"infoCompany": {}}])
def test_invalid_business_input_never_calls_checko(api, changes):
    client, state, _ = api
    assert client.post("/companies", json=dict(BUSINESS, **changes)).status_code == 422
    assert not state["calls"] and not state["session"].stored


def test_numeric_inn_on_http_input_stays_integer(api):
    client, _, _ = api
    assert client.post("/companies", json=dict(BUSINESS, inn=7816435129)).status_code == 201


@pytest.mark.parametrize("inn", [7816435129, 500100732259])
def test_valid_inn_reaches_provider(api, inn):
    client, state, _ = api
    response = client.post("/companies", json=dict(BUSINESS, inn=inn))
    assert response.status_code == 201
    assert response.json()["company"]["inn"] == inn
    assert len(state["calls"]) == 2


@pytest.mark.parametrize("inn", [7816435128, 500100732249, 500100732258])
def test_domain_rejects_incorrect_control_digits(inn):
    with pytest.raises(ValidationError, match="Неверная контрольная цифра ИНН"):
        domain_company(inn)


@pytest.mark.parametrize("inn", [7816435128, 500100732249, 500100732258])
def test_http_rejects_incorrect_control_digits_before_checko(api, inn):
    client, state, _ = api
    assert client.post("/companies", json=dict(BUSINESS, inn=inn)).status_code == 422
    assert not state["calls"] and not state["session"].stored


@pytest.mark.parametrize("inn", ["7816435129", "500100732259", 7816435129.0, True, None, [], {}, -7816435129, 12345678901])
def test_http_rejects_non_integer_or_wrong_length_inn_before_checko(api, inn):
    client, state, _ = api
    assert client.post("/companies", json=dict(BUSINESS, inn=inn)).status_code == 422
    assert not state["calls"] and not state["session"].stored


@pytest.mark.parametrize("inn", ["7816435129", 7816435129.0, True, 10])
def test_dto_uses_domain_inn_type_without_coercion(inn):
    with pytest.raises(ValidationError):
        CreateCompanyDTO(**dict(BUSINESS, inn=inn), user_id=uuid4())


def test_company_is_not_created_without_financials(api):
    client, state, _ = api
    state["no_financials"] = True
    assert client.post("/companies", json=BUSINESS).status_code == 404
    assert not state["session"].stored and not state["uow"].committed


def test_upstream_failure_does_not_persist_company(api):
    client, state, _ = api
    state["upstream_error"] = True
    assert client.post("/companies", json=BUSINESS).status_code == 503
    assert not state["session"].stored


def test_database_commit_failure_rolls_back(api):
    client, state, _ = api
    state["uow"].commit_error = CompanyStorageError()
    assert client.post("/companies", json=BUSINESS).status_code == 503
    assert state["uow"].rolled_back
    assert not state["session"].pending and not state["session"].stored


def test_other_owner_cannot_read_company_but_can_add_same_inn(api):
    client, state, _ = api
    company_id = client.post("/companies", json=BUSINESS).json()["id"]
    state["owner"] = uuid4()
    state["session"].owners.add(state["owner"])
    assert client.get(f"/companies/{company_id}").status_code == 404
    assert client.post("/companies", json=BUSINESS).status_code == 201


def test_missing_local_owner_never_calls_checko(api):
    client, state, _ = api
    state["owner"] = uuid4()
    assert client.post("/companies", json=BUSINESS).status_code == 404
    assert not state["calls"]


def test_authentication_required_for_creation(api):
    client, state, app = api
    del app.dependency_overrides[get_current_user]
    assert client.post("/companies", json=BUSINESS).status_code == 401
    assert not state["calls"]
