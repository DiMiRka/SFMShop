class SFMShopException(Exception):
    pass


class ValidationError(SFMShopException):
    pass


class BusinessLogicError(SFMShopException):
    pass


class NegativePriceError(ValidationError):
    pass


class NegativeQuantityError(ValidationError):
    pass


class InsufficientStockError(BusinessLogicError):
    pass


class InvalidOrderError(BusinessLogicError):
    pass
