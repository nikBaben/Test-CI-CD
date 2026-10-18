from src.modules.users.application.dto import GetUserProfileDTO, UserProfileDTO
from src.modules.users.application.mappers import user_profile_to_dto
from src.modules.users.application.exceptions import UserProfileNotFoundError
from src.modules.users.application.ports.user_unit_of_work import UserUnitOfWork


class GetUserProfileUseCase:
    def __init__(self, uow: UserUnitOfWork):
        self.uow = uow

    async def execute(self, data: GetUserProfileDTO) -> UserProfileDTO:
        user = await self.uow.users.get_by_id(data.user_id)
        if user is None:
            raise UserProfileNotFoundError()
        return user_profile_to_dto(user)
