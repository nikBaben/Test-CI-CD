"""Ошибки получения внешних данных, не зависящие от HTTP и Checko."""


class CompanyDataError(Exception):
    pass


class CompanyNotFoundError(CompanyDataError):
    pass


class FinancialStatementsNotFoundError(CompanyDataError):
    pass


class CompanyDataUnavailableError(CompanyDataError):
    pass


class CompanyDataAccessError(CompanyDataError):
    pass


class CompanyDataFormatError(CompanyDataError):
    pass


class CompanyAlreadyExistsError(CompanyDataError):
    pass


class CompanyOwnerNotFoundError(CompanyDataError):
    pass


class StoredCompanyNotFoundError(CompanyDataError):
    pass


class CompanyStorageError(CompanyDataError):
    pass
