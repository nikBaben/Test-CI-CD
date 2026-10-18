"""Преобразование доменных объектов в выходные DTO use case."""
from src.modules.users.application.dto import TokenDTO, UserProfileDTO
from src.modules.users.domain.auth import TokenPair
from src.modules.users.domain.entities import User


def tokens_to_dto(tokens: TokenPair) -> TokenDTO:
    return TokenDTO(**tokens.model_dump())


def user_profile_to_dto(user: User) -> UserProfileDTO:
    return UserProfileDTO(
        id=user.id, last_name=user.last_name, first_name=user.first_name,
        patronymic=user.patronymic, phone_number=user.phone_number, birthday=user.birthday,
    )
