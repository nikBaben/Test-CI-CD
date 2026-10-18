"""Запускается с TEST_DATABASE_URL, указывающим на отдельную БД *_test."""
import asyncio
import os
from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import delete, inspect
from sqlalchemy.engine import make_url

from src.modules.users.application.exceptions import UserAlreadyExistsError
from src.modules.users.domain.entities import User
from src.modules.users.infrastructure.database.models import UserORM
from src.modules.users.infrastructure.database.unit_of_work import SQLAlchemyUserUnitOfWork
from src.shared.config import DatabaseSettings
from src.shared.database.session import create_database


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="Нужна отдельная PostgreSQL test DB")
def test_postgres_persistence_constraints_and_rollback():
    url = os.environ["TEST_DATABASE_URL"]
    assert (make_url(url).database or "").endswith("_test"), "Тесту нужна отдельная БД *_test"

    async def scenario():
        engine, factory = create_database(DatabaseSettings(_env_file=None, db_url=url))
        user = User.create_user(id=uuid4(), last_name="Иванов", first_name="Иван", patronymic="Иванович",
                                phone_number="79991234567", birthday=date(1995, 5, 20))
        try:
            async with engine.begin() as connection:
                await connection.execute(delete(UserORM))
                columns = await connection.run_sync(lambda conn: inspect(conn).get_columns("users"))
                assert "password" not in {column["name"] for column in columns}
                assert "access_token" not in {column["name"] for column in columns}
            async with factory() as session:
                uow = SQLAlchemyUserUnitOfWork(session)
                await uow.users.add(user)
                await uow.commit()
            async with factory() as session:
                uow = SQLAlchemyUserUnitOfWork(session)
                assert await uow.users.get_by_id(user.id) == user
                assert await uow.users.get_by_phone("79991234567") == user
                duplicate = user.model_copy(update={"id": uuid4()})
                with pytest.raises(UserAlreadyExistsError):
                    await uow.users.add(duplicate)
                await uow.rollback()
            async with factory() as session:
                uow = SQLAlchemyUserUnitOfWork(session)
                rolled_back = user.model_copy(update={"id": uuid4(), "phone_number": "79991234568"})
                await uow.users.add(rolled_back)
                await uow.rollback()
            async with factory() as session:
                assert await SQLAlchemyUserUnitOfWork(session).users.get_by_id(rolled_back.id) is None
        finally:
            async with engine.begin() as connection:
                await connection.execute(delete(UserORM))
            await engine.dispose()
    asyncio.run(scenario())
