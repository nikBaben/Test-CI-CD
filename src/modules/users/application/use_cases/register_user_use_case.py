import logging

from src.modules.users.application.dto import RegisterDTO, RegisterResultDTO
from src.modules.users.application.exceptions import RegistrationIncompleteError, UserAlreadyExistsError, UserStorageError
from src.modules.users.application.ports.identity_provider import IdentityProvider
from src.modules.users.application.ports.user_unit_of_work import UserUnitOfWork
from src.modules.users.domain.entities import User

logger = logging.getLogger(__name__)


class RegisterUserUseCase:
    def __init__(self, provider: IdentityProvider, uow: UserUnitOfWork):
        self.provider = provider
        self.uow = uow

    async def execute(self, data: RegisterDTO) -> RegisterResultDTO:
        if await self.uow.users.get_by_phone(data.phone_number) is not None:
            raise UserAlreadyExistsError()
        user_id = await self.provider.register(
            last_name=data.last_name, first_name=data.first_name, patronymic=data.patronymic,
            phone_number=data.phone_number, birthday=data.birthday, password=data.password.get_secret_value(),
        )
        user = User.create_user(
            id=user_id, first_name=data.first_name, last_name=data.last_name,
            patronymic=data.patronymic, phone_number=data.phone_number, birthday=data.birthday,
        )
        try:
            await self.uow.users.add(user)
        except (UserStorageError, UserAlreadyExistsError):
            try:
                await self.uow.rollback()
            except UserStorageError:
                logger.warning("Rollback connection failed for Keycloak user %s", user_id)
            # flush завершился ошибкой до commit: локальная запись не сохранена.
            try:
                await self.provider.delete_user(user_id)
            except Exception:
                logger.error("Registration compensation failed for Keycloak user %s", user_id)
                raise RegistrationIncompleteError() from None
            raise
        try:
            await self.uow.commit()
        except UserStorageError:
            # При потере соединения во время commit результат может быть неизвестен.
            # Не удаляем идентичность: это может оставить уже сохранённый профиль без неё.
            logger.error("Registration commit needs reconciliation for Keycloak user %s", user_id)
            raise RegistrationIncompleteError() from None
        return RegisterResultDTO(user_id=user_id)
