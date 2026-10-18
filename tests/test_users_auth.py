import asyncio
import json
import threading
import time
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from urllib.parse import parse_qs
from uuid import uuid4

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm
from pydantic import ValidationError

from src.main import create_app
from src.modules.users.application.dto import RegisterDTO
from src.modules.users.infrastructure.deps import get_user_uow
from src.modules.users.infrastructure.keycloak.client import KeycloakClient
from src.shared.config import ServiceSettings
from tests.fakes import MemoryUserUnitOfWork


@pytest.fixture(scope="module")
def keys():
    return [rsa.generate_private_key(public_exponent=65537, key_size=2048) for _ in range(2)]


def jwk(key, kid="key-1"):
    return {**json.loads(RSAAlgorithm.to_jwk(key.public_key())), "kid": kid, "use": "sig", "alg": "RS256"}


@pytest.fixture
def harness(keys):
    # Проверяем настоящий HTTP-запрос PyJWKClient и криптографию, без подмены verify.
    state = {"keys": [jwk(keys[0])], "jwks_status": 200, "jwks_requests": 0, "calls": []}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            state["jwks_requests"] += 1
            self.send_response(state["jwks_status"])
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"keys": state["keys"]}).encode())

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    settings = ServiceSettings(
        _env_file=None, keycloak_url=f"http://127.0.0.1:{server.server_port}",
        keycloak_client_secret="test-login", keycloak_registration_client_secret="test-register",
        jwt_audience="account-api",
        db_url="postgresql+asyncpg://test:test@localhost/unused_test",
    )
    user_id = str(uuid4())

    def token(**changes):
        now = int(time.time())
        claims = {"iss": settings.issuer, "aud": "account-api", "sub": user_id,
                  "exp": now + 300, "iat": now, "typ": "Bearer", "preferred_username": "79991234567"}
        claims.update(changes)
        claims = {k: v for k, v in claims.items() if v is not None}
        return jwt.encode(claims, keys[0], algorithm="RS256", headers={"kid": "key-1"})

    def transport(request):
        state["calls"].append(request)
        if "reply" in state:
            reply = state["reply"]
            if isinstance(reply, Exception):
                raise reply
            return reply
        if request.url.path.endswith("/users"):
            if "admin_reply" in state:
                return state["admin_reply"]
            return httpx.Response(201, headers={"Location": f"{request.url}/{user_id}"})
        form = parse_qs(request.content.decode())
        if form["grant_type"] == ["client_credentials"]:
            return httpx.Response(200, json={"access_token": "service-token"})
        return httpx.Response(200, json={"access_token": token(), "refresh_token": "refresh-value",
                                       "token_type": "Bearer", "expires_in": 300, "refresh_expires_in": 1800})

    app = create_app(settings, keycloak_transport=httpx.MockTransport(transport))
    uow = MemoryUserUnitOfWork()
    app.dependency_overrides[get_user_uow] = lambda: uow
    try:
        with TestClient(app) as client:
            yield client, state, token, user_id, app, settings
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


REGISTER = {"password": "Test-password!", "first_name": "Иван", "last_name": "Иванов",
            "patronymic": "Иванович", "phone_number": "+7 (999) 123-45-67", "birthday": "1995-05-20"}


def test_public_issuer_uses_internal_token_endpoint_and_jwks_url():
    settings = ServiceSettings(
        _env_file=None, keycloak_url="http://keycloak:8080", keycloak_public_url="http://localhost:18081",
        keycloak_client_secret="test-login", keycloak_registration_client_secret="test-register",
        db_url="postgresql+asyncpg://test:test@localhost/unused_test",
    )
    assert settings.issuer == "http://localhost:18081/realms/product-service"
    assert settings.jwks_url == "http://keycloak:8080/realms/product-service/protocol/openid-connect/certs"
    requests = []

    def transport(request):
        requests.append(request)
        return httpx.Response(200, json={
            "access_token": "access", "refresh_token": "refresh", "token_type": "Bearer",
            "expires_in": 300, "refresh_expires_in": 1800,
        })

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as http:
            await KeycloakClient(http, settings).login("79991234567", "password")

    asyncio.run(scenario())
    assert str(requests[0].url) == "http://keycloak:8080/realms/product-service/protocol/openid-connect/token"


def test_public_issuer_is_verified_using_keys_from_internal_address(harness):
    client, state, token, _, _, settings = harness
    settings.keycloak_public_url = "http://public-keycloak.example"
    assert client.get("/users/me", headers={"Authorization": f"Bearer {token()}"}).status_code == 200
    wrong_issuer = f"{settings.keycloak_url}/realms/{settings.keycloak_realm}"
    assert client.get("/users/me", headers={"Authorization": f"Bearer {token(iss=wrong_issuer)}"}).status_code == 401
    assert state["jwks_requests"] == 1


def test_register_login_me_refresh(harness):
    client, state, _, user_id, _, _ = harness
    registered = client.post("/auth/register", json=REGISTER)
    assert registered.status_code == 201
    assert registered.json()["user_id"] == user_id
    service_form = parse_qs(state["calls"][0].content.decode())
    assert service_form["grant_type"] == ["client_credentials"]
    assert service_form["client_id"] == ["backend-registration"]
    assert service_form["client_secret"] == ["test-register"]
    admin_request = state["calls"][1]
    assert admin_request.headers["Authorization"] == "Bearer service-token"
    body = json.loads(admin_request.content)
    assert body["credentials"][0]["value"] == REGISTER["password"]
    assert body["username"] == "79991234567"
    assert "email" not in body
    assert body["firstName"] == "Иван"
    assert body["lastName"] == "Иванов"
    assert body["attributes"] == {"patronymic": ["Иванович"], "phone_number": ["79991234567"], "birthday": ["1995-05-20"]}

    login = client.post("/auth/login", json={"phone_number": "79991234567", "password": REGISTER["password"]})
    assert login.status_code == 200
    assert login.headers["Cache-Control"] == "no-store"
    tokens = login.json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    me = client.get("/users/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["user_id"] == user_id
    assert me.json()["username"] == "79991234567"
    profile = client.get("/users/profile", headers=headers)
    assert profile.status_code == 200
    assert profile.json()["id"] == user_id
    assert profile.json()["phone_number"] == "79991234567"
    assert profile.json()["birthday"] == "1995-05-20"
    assert "password" not in profile.json()
    assert client.get("/users/me", headers=headers).status_code == 200
    assert state["jwks_requests"] == 1  # ключи берутся из кеша
    login_form = parse_qs(state["calls"][2].content.decode())
    assert login_form["grant_type"] == ["password"]
    assert login_form["username"] == ["79991234567"]
    assert "phone_number" not in login_form
    assert login_form["client_id"] == ["backend-login"]
    assert login_form["client_secret"] == ["test-login"]

    refreshed = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert refreshed.status_code == 200
    assert refreshed.headers["Cache-Control"] == "no-store"
    assert parse_qs(state["calls"][3].content.decode())["grant_type"] == ["refresh_token"]


@pytest.mark.parametrize("authorization", [None, "Basic abc", "Bearer", "Bearer garbage"])
def test_missing_or_malformed_token(harness, authorization):
    client, state, *_ = harness
    response = client.get("/users/me", headers={"Authorization": authorization} if authorization else {})
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert state["jwks_requests"] == 0


@pytest.mark.parametrize("claims", [
    {"exp": 1}, {"iat": 9999999999}, {"nbf": 9999999999},
    {"iss": "https://other.example/realms/other"}, {"aud": "orders-api"},
    {"typ": "Refresh"}, {"typ": "ID"}, {"typ": None}, {"sub": ""}, {"sub": " "}, {"sub": 123},
    *[{name: None} for name in ("exp", "iat", "iss", "aud", "sub")],
])
def test_reject_invalid_claims(harness, claims):
    client, _, token, *_ = harness
    response = client.get("/users/me", headers={"Authorization": f"Bearer {token(**claims)}"})
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_accept_multiple_audiences(harness):
    client, _, token, *_ = harness
    assert client.get("/users/me", headers={"Authorization": f"Bearer {token(aud=['account', 'account-api'])}"}).status_code == 200


def test_wrong_signature_and_algorithm(harness, keys):
    client, _, token, *_ = harness
    claims = jwt.decode(token(), options={"verify_signature": False})
    for bad in [jwt.encode(claims, keys[1], algorithm="RS256", headers={"kid": "key-1"}),
                jwt.encode(claims, "a-long-secret-for-hs256-that-is-at-least-32-bytes", algorithm="HS256", headers={"kid": "key-1"}),
                jwt.encode(claims, "", algorithm="none")]:
        assert client.get("/users/me", headers={"Authorization": f"Bearer {bad}"}).status_code == 401


def test_jwks_outage_is_503(harness):
    client, state, token, *_ = harness
    state["jwks_status"] = 503
    assert client.get("/users/me", headers={"Authorization": f"Bearer {token()}"}).status_code == 503


def test_key_rotation_and_unknown_kid(harness, keys, monkeypatch):
    client, state, token, *_ = harness
    assert client.get("/users/me", headers={"Authorization": f"Bearer {token()}"}).status_code == 200
    claims = jwt.decode(token(), options={"verify_signature": False})
    state["keys"] = [jwk(keys[1], "key-2")]
    rotated = jwt.encode(claims, keys[1], algorithm="RS256", headers={"kid": "key-2"})
    # PyJWT ограничивает обновление JWKS по неизвестному kid: 30 секунд.
    assert client.get("/users/me", headers={"Authorization": f"Bearer {rotated}"}).status_code == 401
    assert state["jwks_requests"] == 1
    clock_after_cooldown = time.monotonic() + 31
    monkeypatch.setattr(jwt.jwks_client, "time", SimpleNamespace(monotonic=lambda: clock_after_cooldown))
    assert client.get("/users/me", headers={"Authorization": f"Bearer {rotated}"}).status_code == 200
    unknown = jwt.encode(claims, keys[1], algorithm="RS256", headers={"kid": "unknown"})
    assert client.get("/users/me", headers={"Authorization": f"Bearer {unknown}"}).status_code == 401


@pytest.mark.parametrize("path,payload,status,error,expected", [
    ("/auth/login", {"phone_number": "79991234567", "password": "wrong"}, 400, "invalid_grant", 401),
    ("/auth/refresh", {"refresh_token": "bad"}, 400, "invalid_grant", 401),
    ("/auth/login", {"phone_number": "79991234567", "password": "wrong"}, 401, "invalid_client", 502),
    ("/auth/login", {"phone_number": "79991234567", "password": "wrong"}, 500, "server_error", 502),
])
def test_oauth_errors(harness, path, payload, status, error, expected):
    client, state, *_ = harness
    state["reply"] = httpx.Response(status, json={"error": error})
    response = client.post(path, json=payload)
    assert response.status_code == expected
    assert response.headers["Cache-Control"] == "no-store"
    assert "wrong" not in response.text


@pytest.mark.parametrize("response", [httpx.Response(200, text="html"), httpx.Response(200, json=[]),
                                      httpx.Response(200, json={"access_token": "only-access"}),
                                      httpx.Response(500, text="html")])
def test_malformed_keycloak_response(harness, response):
    client, state, *_ = harness
    state["reply"] = response
    assert client.post("/auth/login", json={"phone_number": "79991234567", "password": "test"}).status_code == 502


def test_network_error(harness):
    client, state, *_ = harness
    state["reply"] = httpx.ConnectError("Keycloak unavailable")
    assert client.post("/auth/login", json={"phone_number": "79991234567", "password": "test"}).status_code == 503


@pytest.mark.parametrize("status,expected", [(409, 409), (400, 422), (403, 502), (500, 502)])
def test_registration_admin_errors(harness, status, expected):
    client, state, *_ = harness
    state["admin_reply"] = httpx.Response(status)
    assert client.post("/auth/register", json=REGISTER).status_code == expected


@pytest.mark.parametrize("data", [
    dict(REGISTER, phone_number="123"), dict(REGISTER, phone_number="+7 (999) abc-45-67"),
    dict(REGISTER, phone_number="74951234567"), dict(REGISTER, birthday="20.05.1995"),
    dict(REGISTER, birthday="1995-02-30"), dict(REGISTER, birthday="9999-01-01"),
    dict(REGISTER, first_name="  "), dict(REGISTER, patronymic=""), dict(REGISTER, password=""),
    dict(REGISTER, username="legacy"), dict(REGISTER, email="legacy@example.com"),
])
def test_invalid_registration_never_calls_keycloak(harness, data):
    client, state, *_ = harness
    assert client.post("/auth/register", json=data).status_code == 422
    assert state["calls"] == []


@pytest.mark.parametrize("field", ["last_name", "first_name", "patronymic", "phone_number", "birthday", "password"])
def test_all_registration_fields_required(harness, field):
    client, state, *_ = harness
    payload = {key: value for key, value in REGISTER.items() if key != field}
    assert client.post("/auth/register", json=payload).status_code == 422
    assert state["calls"] == []


def test_registration_dto_has_typed_date_and_secret():
    dto = RegisterDTO(**dict(REGISTER, phone_number="8 (999) 123-45-67"))
    assert dto.phone_number == "79991234567"
    assert dto.birthday == date(1995, 5, 20)
    assert dto.password.get_secret_value() == REGISTER["password"]
    assert REGISTER["password"] not in repr(dto)
    with pytest.raises(ValidationError):
        RegisterDTO(**dict(REGISTER, phone_number="bad"))


def test_validation_does_not_echo_password(harness):
    client, *_ = harness
    response = client.post("/auth/login", json={"phone_number": "79991234567", "password": 123456789})
    assert response.status_code == 422
    assert "123456789" not in response.text


@pytest.mark.parametrize("phone", ["79991234567", "+7 (999) 123-45-67", "8 (999) 123-45-67"])
def test_login_normalizes_phone_before_keycloak(harness, phone):
    client, state, *_ = harness
    response = client.post("/auth/login", json={"phone_number": phone, "password": "test"})
    assert response.status_code == 200
    form = parse_qs(state["calls"][0].content.decode())
    assert form["username"] == ["79991234567"]
    assert "phone_number" not in form


@pytest.mark.parametrize("payload", [
    {"username": "79991234567", "password": "test"},
    {"phone_number": "bad", "password": "test"},
    {"phone_number": "79991234567", "username": "legacy", "password": "test"},
])
def test_login_rejects_invalid_phone_or_old_username_field(harness, payload):
    client, state, *_ = harness
    assert client.post("/auth/login", json=payload).status_code == 422
    assert state["calls"] == []


def test_openapi_documents_bearer(harness):
    client, *_ = harness
    schema = client.get("/openapi.json").json()
    assert schema["paths"]["/users/me"]["get"]["security"] == [{"HTTPBearer": []}]
    assert "security" not in schema["paths"]["/auth/login"]["post"]
    registration = schema["components"]["schemas"]["RegisterRequest"]
    assert set(registration["properties"]) == set(REGISTER)
    assert set(registration["required"]) == set(REGISTER)
    assert registration["properties"]["birthday"]["format"] == "date"
    login = schema["components"]["schemas"]["LoginRequest"]
    assert set(login["properties"]) == {"phone_number", "password"}
    assert set(login["required"]) == {"phone_number", "password"}
