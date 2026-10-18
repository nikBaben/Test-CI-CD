"""Ошибки сценариев users, независимые от HTTP."""


class IdentityProviderError(Exception):
    pass


class InvalidCredentialsError(IdentityProviderError):
    pass


class InvalidRefreshTokenError(IdentityProviderError):
    pass


class InvalidUserDataError(IdentityProviderError):
    pass


class UserAlreadyExistsError(IdentityProviderError):
    pass


class IdentityProviderPermissionError(IdentityProviderError):
    pass


class IdentityProviderUnavailableError(IdentityProviderError):
    pass


class IdentityProviderUnexpectedError(IdentityProviderError):
    pass


class UserStorageError(IdentityProviderError):
    pass


class RegistrationIncompleteError(IdentityProviderError):
    pass


class UserProfileNotFoundError(IdentityProviderError):
    pass
