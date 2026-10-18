from src.modules.users.application.dto import LoginDTO, TokenDTO
from src.modules.users.application.mappers import tokens_to_dto
from src.modules.users.application.ports.identity_provider import IdentityProvider


class LoginUserUseCase:
    def __init__(self, provider: IdentityProvider):
        self.provider = provider

    async def execute(self, data: LoginDTO) -> TokenDTO:
        tokens = await self.provider.login(data.phone_number, data.password.get_secret_value())
        return tokens_to_dto(tokens)
