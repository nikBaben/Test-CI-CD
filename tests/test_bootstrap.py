import asyncio
from contextlib import asynccontextmanager

import httpx
import pytest
from fastapi import FastAPI

import src.modules.companies.infrastructure.bootstrap as bootstrap
from src.shared.config import PROJECT_ROOT, ServiceSettings


@pytest.mark.parametrize("failure", ["broker", "outbox"])
def test_company_startup_failure_closes_created_resources(monkeypatch, failure):
    async def scenario():
        app = FastAPI()
        app.state.session_factory = object()
        settings = ServiceSettings(
            _env_file=None, db_url="postgresql+asyncpg://test:test@localhost/unused_test",
            keycloak_client_secret="test", keycloak_registration_client_secret="test", checko_api_key="test",
        )
        client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200)))
        broker_closed = []

        @asynccontextmanager
        async def messaging(*args, **kwargs):
            if failure == "broker":
                raise RuntimeError("broker startup failed")
            try:
                yield object()
            finally:
                broker_closed.append(True)

        @asynccontextmanager
        async def outbox(*args, **kwargs):
            raise RuntimeError("outbox startup failed")
            yield  # async context manager должен быть асинхронным генератором.

        monkeypatch.setattr(bootstrap.httpx, "AsyncClient", lambda **kwargs: client)
        monkeypatch.setattr(bootstrap, "messaging_lifespan", messaging)
        monkeypatch.setattr(bootstrap, "outbox_lifespan", outbox)
        with pytest.raises(RuntimeError, match=failure):
            async with bootstrap.companies_lifespan(app, settings):
                pytest.fail("Неуспешный bootstrap не должен запускать приложение")
        assert client.is_closed
        assert broker_closed == ([True] if failure == "outbox" else [])
        assert not hasattr(app.state, "checko_client")
        assert not hasattr(app.state, "publishers")
        assert not hasattr(app.state, "outbox_dispatcher")

    asyncio.run(scenario())


def test_settings_project_root_survives_src_layout():
    assert (PROJECT_ROOT / "pyproject.toml").is_file()
    assert (PROJECT_ROOT / "src/main.py").is_file()
