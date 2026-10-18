class DocumentError(Exception):
    pass


class DocumentValidationError(DocumentError, ValueError):
    pass


class DocumentTooLargeError(DocumentError):
    pass


class DocumentNotFoundError(DocumentError):
    pass


class DocumentCompanyNotFoundError(DocumentError):
    pass


class DocumentStorageError(DocumentError):
    pass
