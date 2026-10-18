from src.modules.users.application.dto import RefreshDTO, TokenDTO
from src.modules.users.application.mappers import tokens_to_dto
from src.modules.users.application.ports.identity_provider import IdentityProvider


class RefreshTokensUseCase:
    def __init__(self, provider: IdentityProvider):
        self.provider = provider

    async def execute(self, data: RefreshDTO) -> TokenDTO:
        tokens = await self.provider.refresh(data.refresh_token.get_secret_value())
        return tokens_to_dto(tokens)
