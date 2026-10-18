"""Настройки из окружения; .env читается относительно корня проекта."""
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class CheckoSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env", env_file_encoding="utf-8", extra="ignore",
    )

    checko_api_key: SecretStr | None = None
    checko_base_url: str = "https://api.checko.ru/v2/"
    checko_timeout_seconds: float = Field(default=20, gt=0)


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env", env_file_encoding="utf-8", extra="ignore",
    )

    db_url: SecretStr
    db_pool_size: int = Field(default=5, gt=0)
    db_max_overflow: int = Field(default=10, ge=0)
    db_pool_timeout: int = Field(default=30, gt=0)
    db_pool_recycle_sec: int = Field(default=1800, gt=0)
    db_pool_pre_ping: bool = True


class KeycloakSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env", env_file_encoding="utf-8", extra="ignore",
    )

    keycloak_url: str = "http://localhost:8080"
    keycloak_public_url: str | None = None
    keycloak_realm: str = "product-service"
    keycloak_client_id: str = "backend-login"
    keycloak_client_secret: SecretStr = Field(min_length=1)
    keycloak_registration_client_id: str = "backend-registration"
    keycloak_registration_client_secret: SecretStr = Field(min_length=1)
    jwt_audience: str = Field(default="account-api", min_length=1)
    keycloak_timeout_seconds: float = Field(default=10, gt=0)
    jwks_cache_seconds: int = Field(default=300, gt=0)
    jwks_timeout_seconds: float = Field(default=5, gt=0)
    jwt_leeway_seconds: int = Field(default=5, ge=0)

    @property
    def issuer(self) -> str:
        public_url = self.keycloak_public_url or self.keycloak_url
        return f"{public_url.rstrip('/')}/realms/{self.keycloak_realm}"

    @property
    def token_url(self) -> str:
        return f"{self.keycloak_url.rstrip('/')}/realms/{self.keycloak_realm}/protocol/openid-connect/token"

    @property
    def jwks_url(self) -> str:
        return f"{self.keycloak_url.rstrip('/')}/realms/{self.keycloak_realm}/protocol/openid-connect/certs"

class RabbitMQSettings(BaseSettings):
    """Настройки из аргументов, переменных RABBITMQ_* и файла .env."""

    model_config = SettingsConfigDict(
        env_prefix="RABBITMQ_",
        env_file=PROJECT_ROOT / ".env",
        extra="ignore",
        validate_assignment=True,  # Проверяем значения и при изменении полей.
    )

    # Если URL задан, адрес и учётные данные берутся из него.
    # Для раздельных host/port/login/password укажите url=None.
    url: str | None = "amqp://guest:guest@localhost/"
    host: str = "localhost"
    port: int = Field(default=5672, ge=1, le=65535)
    login: str = "guest"
    password: str = Field(default="guest", repr=False)
    virtualhost: str = "/"
    ssl: bool = False

    # Интервалы и таймаут подключения задаются в секундах.
    heartbeat: int = Field(default=60, ge=0)
    reconnect_interval: float = Field(default=5, gt=0)
    connect_timeout: float | None = Field(default=10, gt=0)
    fail_fast: bool = True
    # Максимум неподтверждённых сообщений у обработчика; 0 снимает ограничение.
    prefetch_count: int = Field(default=10, ge=0)


class DocumentSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env", env_file_encoding="utf-8", extra="ignore",
    )

    minio_endpoint: str = "localhost:19000"
    minio_access_key: SecretStr | None = None
    minio_secret_key: SecretStr | None = None
    minio_secure: bool = False
    minio_region: str = "us-east-1"
    minio_bucket: str = "company-documents"
    minio_timeout_seconds: float = Field(default=10, gt=0)
    document_max_bytes: int = Field(default=20 * 1024 * 1024, gt=0)
    document_cleanup_interval_seconds: int = Field(default=300, ge=1)
    document_cleanup_grace_seconds: int = Field(default=3600, ge=60)


class ServiceSettings(KeycloakSettings, DatabaseSettings, CheckoSettings, DocumentSettings):
    app_name: str = "Account Service"
    rabbitmq_publish_timeout_seconds: float = Field(default=5, gt=0)
    outbox_poll_interval_seconds: float = Field(default=1, gt=0)
    outbox_batch_size: int = Field(default=25, ge=1)
    outbox_retry_seconds: float = Field(default=2, gt=0)
    outbox_max_retry_seconds: float = Field(default=60, gt=0)
