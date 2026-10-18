import asyncio

from alembic import context

from src.modules.users.infrastructure.database.models import UserORM
from src.modules.companies.infrastructure.database.models import CompanyORM, CompanyFinanceORM, CompanyEconomicSectorORM
from src.modules.documents.infrastructure.database.models import CompanyDocumentORM
from src.modules.companies.infrastructure.database.outbox_models import OutboxEventORM
from src.shared.config import DatabaseSettings, PROJECT_ROOT
from src.shared.database.session import create_database

target_metadata = UserORM.metadata


def settings() -> DatabaseSettings:
    env_file = context.get_x_argument(as_dictionary=True).get("env_file", ".env")
    return DatabaseSettings(_env_file=PROJECT_ROOT / env_file)


def run_sync_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_online():
    engine, _ = create_database(settings())
    try:
        async with engine.connect() as connection:
            await connection.run_sync(run_sync_migrations)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    context.configure(url=settings().db_url.get_secret_value(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(run_online())
