"""Контракты границ: HTTP schema ↔ DTO ↔ use case ↔ domain/ports."""
import ast
import asyncio
import importlib.util
from datetime import date
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from src.main import create_app
from src.modules.companies.application.dto import CompanyDTO, StoredCompanyDTO
from src.modules.companies.application.mappers import company_to_dto
from src.modules.companies.presentation.http.schemas.respones_schemas import CompanyResponse
from src.modules.users.application.dto import GetUserProfileDTO, LoginDTO, RefreshDTO, TokenDTO, UserProfileDTO
from src.modules.users.application.use_cases.login_user_use_case import LoginUserUseCase
from src.modules.users.application.use_cases.refresh_tokens_use_case import RefreshTokensUseCase
from src.modules.users.application.use_cases.get_user_profile_use_case import GetUserProfileUseCase
from src.modules.users.domain.auth import TokenPair
from src.modules.users.domain.entities import User
from src.shared.config import ServiceSettings
from tests.fakes import MemoryUserUnitOfWork
from tests.test_companies_business import domain_company


def test_product_imports_are_absolute_and_resolve_from_project_root():
    root = Path(__file__).resolve().parents[1]
    paths = list((root / "src").rglob("*.py"))
    assert paths
    for path in paths:
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom):
                assert node.level == 0, path
                names = [node.module or ""]
            elif isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            else:
                continue
            for name in names:
                assert name.split(".")[0] not in {"modules", "shared", "app"}, (path, name)
                if name.startswith("src."):
                    assert importlib.util.find_spec(name) is not None, (path, name)


def test_schema_and_dto_imports_stay_at_their_boundaries():
    root = Path(__file__).resolve().parents[1]
    paths = list((root / "src/modules").rglob("*.py"))
    assert paths, "Не найдены файлы модулей для проверки границ"
    for path in paths:
        relative = path.relative_to(root).as_posix()
        imports = [node.module or "" for node in ast.walk(ast.parse(path.read_text())) if isinstance(node, ast.ImportFrom)]
        if "/companies/application/" in relative:
            assert not any(".infrastructure." in name for name in imports), relative
        if "/companies/application/use_cases/" in relative:
            assert not any(name.startswith("src.shared.rabbitmq") for name in imports), relative
        if any(part in relative for part in ("/infrastructure/", "/domain/", "/application/ports/")):
            assert not any(name.endswith(".application.dto") for name in imports), relative
        if "/presentation/http/" not in relative:
            assert not any(".presentation.http.schemas." in name for name in imports), relative
        if relative.endswith("/application/dto.py") or "/presentation/http/schemas/" in relative:
            assert not any(name.endswith(".domain.entities") for name in imports), relative
        if "/presentation/http/schemas/" in relative:
            assert not any(name.endswith(".application.dto") for name in imports), relative


def test_company_result_dto_and_response_do_not_share_domain_objects():
    entity = domain_company()
    dto = company_to_dto(entity)
    assert type(dto) is CompanyDTO
    response = CompanyResponse.model_validate(StoredCompanyDTO(id=uuid4(), company=dto))
    original_name = dto.infoCompany.name
    original_profit = dto.financials.net_profit
    entity.infoCompany.name = "Изменение внутри домена"
    entity.financials.net_profit = 0
    entity.infoCompany.economicSectorCompany.clear()
    assert dto.infoCompany.name == response.company.infoCompany.name == original_name
    assert dto.financials.net_profit == response.company.financials.net_profit == original_profit
    assert len(dto.infoCompany.economicSectorCompany) == len(response.company.infoCompany.economicSectorCompany) == 3


def test_profile_usecase_returns_a_detached_dto():
    async def scenario():
        user = User.create_user(id=uuid4(), first_name="Иван", last_name="Иванов", patronymic="Иванович",
                                phone_number="79991234567", birthday=date(1995, 5, 20))
        uow = MemoryUserUnitOfWork()
        await uow.users.add(user)
        await uow.commit()
        result = await GetUserProfileUseCase(uow).execute(GetUserProfileDTO(user_id=user.id))
        assert type(result) is UserProfileDTO
        user.first_name = "Другое имя"
        assert result.first_name == "Иван"
    asyncio.run(scenario())


def test_token_usecases_return_dto_instead_of_provider_domain_value():
    async def scenario():
        tokens = TokenPair(access_token="access", refresh_token="refresh", token_type="Bearer",
                           expires_in=300, refresh_expires_in=1800)

        class Provider:
            async def login(self, phone_number, password):
                assert phone_number == "79991234567" and password == "password"
                return tokens

            async def refresh(self, refresh_token):
                assert refresh_token == "refresh"
                return tokens

        provider = Provider()
        logged_in = await LoginUserUseCase(provider).execute(LoginDTO(phone_number="79991234567", password="password"))
        refreshed = await RefreshTokensUseCase(provider).execute(RefreshDTO(refresh_token="refresh"))
        assert type(logged_in) is type(refreshed) is TokenDTO
        assert logged_in.model_dump() == refreshed.model_dump() == tokens.model_dump()
    asyncio.run(scenario())


def test_openapi_uses_http_models_instead_of_dto_or_domain_entities():
    app = create_app(ServiceSettings(
        _env_file=None, keycloak_client_secret="test", keycloak_registration_client_secret="test",
        db_url="postgresql+asyncpg://test:test@localhost/unused_test",
    ))
    with TestClient(app) as client:
        schema = client.get("/openapi.json").json()
    models = schema["components"]["schemas"]
    assert not any(name.endswith("DTO") for name in models)
    assert not {"Company", "InfoCompany", "FinancialInfoCompany", "EconomicSectorCompany", "User"}.intersection(models)
    assert {"CompanyResponse", "CheckoCompanyResponse", "TokenResponse", "UserProfileResponse"}.issubset(models)
