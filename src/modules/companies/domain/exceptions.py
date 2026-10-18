class CompanyValidationError(ValueError):
    """Нарушено правило создания компании."""


class InvalidCompanyInnError(CompanyValidationError):
    pass


class InvalidCompanyTaxRegimeError(CompanyValidationError):
    pass
