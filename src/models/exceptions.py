class SFMShopException(Exception):
    pass


class ValidationError(SFMShopException):
    pass


class BusinessLogicError(SFMShopException):
    pass


class NegativeValidationError(ValidationError):
    pass


class InsufficientStockError(BusinessLogicError):
    pass


class InvalidOrderError(BusinessLogicError):
    pass
