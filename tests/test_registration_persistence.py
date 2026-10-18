import asyncio
from uuid import uuid4

import pytest

from src.modules.users.application.dto import RegisterDTO
from src.modules.users.application.exceptions import (
    IdentityProviderUnavailableError, RegistrationIncompleteError,
    UserAlreadyExistsError, UserStorageError,
)
from src.modules.users.application.use_cases.register_user_use_case import RegisterUserUseCase
from tests.fakes import MemoryUserUnitOfWork


class Provider:
    def __init__(self):
        self.user_id = uuid4()
        self.created = False
        self.deleted = False
        self.register_error = None
        self.delete_error = None

    async def register(self, **registration):
        if self.register_error:
            raise self.register_error
        self.created = True
        return self.user_id

    async def delete_user(self, user_id):
        assert user_id == self.user_id
        if self.delete_error:
            raise self.delete_error
        self.deleted = True


def data():
    return RegisterDTO(last_name="Иванов", first_name="Иван", patronymic="Иванович",
                       phone_number="79991234567", birthday="1995-05-20", password="test")


def test_profile_saved_with_keycloak_id():
    async def scenario():
        provider, uow = Provider(), MemoryUserUnitOfWork()
        result = await RegisterUserUseCase(provider, uow).execute(data())
        assert result.user_id == provider.user_id
        assert uow.committed
        assert uow.stored[result.user_id].phone_number == "79991234567"
        assert not hasattr(uow.stored[result.user_id], "password")
        with pytest.raises(UserAlreadyExistsError):
            await RegisterUserUseCase(Provider(), uow).execute(data())
    asyncio.run(scenario())


def test_keycloak_failure_does_not_save_profile():
    async def scenario():
        provider, uow = Provider(), MemoryUserUnitOfWork()
        provider.register_error = IdentityProviderUnavailableError()
        with pytest.raises(IdentityProviderUnavailableError):
            await RegisterUserUseCase(provider, uow).execute(data())
        assert not uow.stored and not uow.pending and not uow.committed
    asyncio.run(scenario())


@pytest.mark.parametrize("failure", [UserStorageError(), UserAlreadyExistsError()])
def test_flush_failure_rolls_back_and_compensates(failure):
    async def scenario():
        provider, uow = Provider(), MemoryUserUnitOfWork()
        uow.add_error = failure
        with pytest.raises(type(failure)):
            await RegisterUserUseCase(provider, uow).execute(data())
        assert provider.created and provider.deleted and uow.rolled_back
        assert not uow.stored
    asyncio.run(scenario())


def test_compensation_failure_is_reported():
    async def scenario():
        provider, uow = Provider(), MemoryUserUnitOfWork()
        uow.add_error = UserStorageError()
        provider.delete_error = IdentityProviderUnavailableError()
        with pytest.raises(RegistrationIncompleteError):
            await RegisterUserUseCase(provider, uow).execute(data())
    asyncio.run(scenario())


def test_unknown_commit_outcome_does_not_delete_keycloak_identity():
    async def scenario():
        provider, uow = Provider(), MemoryUserUnitOfWork()
        uow.commit_error = UserStorageError()
        with pytest.raises(RegistrationIncompleteError):
            await RegisterUserUseCase(provider, uow).execute(data())
        assert provider.created and not provider.deleted
    asyncio.run(scenario())
