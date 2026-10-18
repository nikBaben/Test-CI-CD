from uuid import uuid4

import pytest

from src.modules.companies.application.events import CompanyUpdated
from src.modules.companies.domain.enums import EconomicsSectors
from src.modules.users.infrastructure.deps import get_current_user
from tests.test_companies_business import BUSINESS, api


NEW_INN = 7707083893
NEW_INFO = {
    "ОГРН": "1027700132195", "НаимСокр": "Новая компания", "НаимПолн": "Новое полное название",
    "ДатаРег": "2020-01-01", "ЮрАдрес": {"НасПункт": "г. Москва"}, "СЧР": 10, "СЧРГод": 2024,
    "ОКВЭД": {"Код": "62.01", "Наим": "Разработка программного обеспечения"},
    "ОКВЭДДоп": [{"Код": "63.11", "Наим": "Обработка данных"}],
}
NEW_FINANCES = {"2024": {"2110": 1000, "2120": 600, "2220": 10, "2400": 100}}


def create_company(api, **changes):
    client, state, _ = api
    response = client.post("/companies", json=dict(BUSINESS, **changes))
    assert response.status_code == 201
    state["calls"].clear()
    state["uow"].committed = False
    state["uow"].rolled_back = False
    state["outbox"].add.reset_mock()
    return response.json()


def test_patch_business_fields_preserves_checko_data_without_requests(api):
    original = create_company(api)
    client, state, _ = api
    changes = {
        "sales_model": "B2C", "primary_sales_channel": "marketplace", "tax_regime": "OSNO",
        "seasonality": "Summer/Spring_Peak", "key_vulnerability": "High_Reliance_Loans_Leasing",
        "ceo_goal": "Maintaining_Market_Position_Cost_Optimization",
    }
    response = client.patch("/companies/" + original["id"], json=changes)
    assert response.status_code == 200
    result = response.json()
    assert result["id"] == original["id"]
    for request_field, response_field in {
        "sales_model": "salesModel", "primary_sales_channel": "primarySalesChannel", "tax_regime": "taxRegime",
        "seasonality": "seasonality", "key_vulnerability": "keyVulnerability", "ceo_goal": "CEOGoal",
    }.items():
        assert result["company"][response_field] == changes[request_field]
    for field in ("inn", "infoCompany", "financials"):
        assert result["company"][field] == original["company"][field]
    assert not state["calls"] and state["uow"].committed
    assert client.get("/companies/" + original["id"]).json() == result
    state["outbox"].add.assert_awaited_once()
    event = state["outbox"].add.await_args.args[0]
    assert isinstance(event, CompanyUpdated)
    assert str(event.company_id) == result["id"] and event.user_id == state["owner"]
    assert event.company.model_dump(mode="json") == result["company"]


@pytest.mark.parametrize("changes", [{}, {"inn": BUSINESS["inn"]}, {"sales_model": BUSINESS["sales_model"]}])
def test_empty_or_unchanged_patch_does_not_call_checko(api, changes):
    original = create_company(api)
    client, state, _ = api
    response = client.patch("/companies/" + original["id"], json=changes)
    assert response.status_code == 200 and response.json() == original
    assert not state["calls"] and state["uow"].committed
    state["outbox"].add.assert_not_awaited()


def test_explicit_unchanged_inn_with_business_changes_creates_updated_event(api):
    original = create_company(api)
    client, state, _ = api
    response = client.patch("/companies/" + original["id"], json={"inn": BUSINESS["inn"], "sales_model": "B2C"})
    assert response.status_code == 200 and not state["calls"]
    state["outbox"].add.assert_awaited_once()
    event = state["outbox"].add.await_args.args[0]
    assert isinstance(event, CompanyUpdated)
    assert event.company.model_dump(mode="json") == response.json()["company"]


def test_changed_inn_refreshes_info_activities_global_sector_and_finances(api):
    original = create_company(api)
    client, state, _ = api
    state.update(checko_info=NEW_INFO, checko_finances=NEW_FINANCES)
    response = client.patch("/companies/" + original["id"], json={"inn": NEW_INN, "sales_model": "B2G"})
    assert response.status_code == 200
    company = response.json()["company"]
    assert response.json()["id"] == original["id"] and company["inn"] == NEW_INN
    assert company["salesModel"] == "B2G" and company["taxRegime"] == original["company"]["taxRegime"]
    assert company["infoCompany"]["name"] == NEW_INFO["НаимСокр"]
    assert company["infoCompany"]["ogrn"] == NEW_INFO["ОГРН"]
    assert company["infoCompany"]["primaryEconomicSectorCompany"]["globalSector"] == EconomicsSectors.J.value
    assert [item["classOkved"] for item in company["infoCompany"]["economicSectorCompany"]] == [63]
    assert company["financials"]["year"] == 2024 and company["financials"]["revenue"] == "1000"
    assert len(state["calls"]) == 2
    assert all(request.url.params["inn"] == str(NEW_INN) for request in state["calls"])
    assert client.get("/companies/" + original["id"]).json() == response.json()
    state["outbox"].add.assert_not_awaited()


def test_tax_rule_uses_merged_inn_and_tax_before_checko(api):
    original = create_company(api, inn=500100732259, tax_regime="NPD")
    client, state, _ = api
    response = client.patch("/companies/" + original["id"], json={"inn": NEW_INN})
    assert response.status_code == 422
    assert not state["calls"] and client.get("/companies/" + original["id"]).json() == original
    response = client.patch("/companies/" + original["id"], json={"inn": NEW_INN, "tax_regime": "USN"})
    assert response.status_code == 200 and len(state["calls"]) == 2


@pytest.mark.parametrize("changes", [
    {"inn": "7707083893"}, {"inn": 7707083893.0}, {"inn": True}, {"inn": 10}, {"inn": 7707083892},
    {"inn": None}, {"sales_model": None}, {"sales_model": "invalid"}, {"tax_regime": "NPD"},
])
def test_bad_patch_rejected_without_touching_company_or_checko(api, changes):
    original = create_company(api)
    client, state, _ = api
    assert client.patch("/companies/" + original["id"], json=changes).status_code == 422
    assert not state["calls"]
    assert client.get("/companies/" + original["id"]).json() == original


@pytest.mark.parametrize("field", ["user_id", "company_id", "infoCompany", "financials", "ogrn", "global_sector"])
def test_patch_cannot_change_owner_or_external_data(api, field):
    original = create_company(api)
    client, state, _ = api
    assert client.patch("/companies/" + original["id"], json={field: "forbidden"}).status_code == 422
    assert not state["calls"]
    assert client.get("/companies/" + original["id"]).json() == original


def test_unknown_and_other_owners_company_are_not_updated(api):
    original = create_company(api)
    client, state, _ = api
    assert client.patch("/companies/" + str(uuid4()), json={"inn": NEW_INN}).status_code == 404
    state["owner"] = uuid4()
    assert client.patch("/companies/" + original["id"], json={"inn": NEW_INN}).status_code == 404
    assert not state["calls"]


def test_duplicate_inn_rejected_before_checko(api):
    original = create_company(api)
    create_company(api, inn=NEW_INN)
    client, state, _ = api
    assert client.patch("/companies/" + original["id"], json={"inn": NEW_INN}).status_code == 409
    assert not state["calls"]
    assert client.get("/companies/" + original["id"]).json() == original


@pytest.mark.parametrize("failure,status", [("upstream_error", 503), ("no_financials", 404)])
def test_checko_failure_keeps_every_saved_field(api, failure, status):
    original = create_company(api)
    client, state, _ = api
    state[failure] = True
    assert client.patch("/companies/" + original["id"], json={"inn": NEW_INN}).status_code == status
    assert state["uow"].rolled_back and not state["session"].pending
    assert client.get("/companies/" + original["id"]).json() == original


def test_commit_failure_rolls_back_update(api):
    from src.modules.companies.application.exceptions import CompanyStorageError

    original = create_company(api)
    client, state, _ = api
    state["uow"].commit_error = CompanyStorageError()
    assert client.patch("/companies/" + original["id"], json={"inn": NEW_INN}).status_code == 503
    assert state["uow"].rolled_back and not state["session"].pending
    assert client.get("/companies/" + original["id"]).json() == original


def test_business_patch_works_without_checko_configuration(api):
    original = create_company(api)
    client, state, app = api
    app.state.checko_client = None
    assert client.patch("/companies/" + original["id"], json={"sales_model": "B2C"}).status_code == 200
    assert client.patch("/companies/" + original["id"], json={"inn": NEW_INN}).status_code == 503
    assert not state["calls"]
    saved = client.get("/companies/" + original["id"]).json()["company"]
    assert saved["inn"] == BUSINESS["inn"] and saved["salesModel"] == "B2C"


def test_authentication_required_for_patch(api):
    original = create_company(api)
    client, state, app = api
    del app.dependency_overrides[get_current_user]
    assert client.patch("/companies/" + original["id"], json={"inn": NEW_INN}).status_code == 401
    assert not state["calls"]
