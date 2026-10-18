from uuid import UUID

from pydantic import BaseModel

from src.modules.users.domain.value_objects import Birthday, PersonName, PhoneNumber


class User(BaseModel):
    """Сущность 'Пользователь'."""
    id: UUID
    first_name: PersonName
    last_name: PersonName
    patronymic: PersonName
    phone_number: PhoneNumber
    birthday: Birthday

    @classmethod
    def create_user(
        cls, 
        id: UUID,
        first_name: str, 
        last_name:  str, 
        patronymic: str,
        phone_number: str, 
        birthday: Birthday,
    ) -> User:
        return cls(
            id = id,
            first_name = first_name,
            last_name = last_name,
            patronymic = patronymic,
            phone_number = phone_number,
            birthday = birthday
        )
        
