class SFMShopException(Exception):
    pass


class ValidationError(SFMShopException):
    pass


class NotFoundError(ValidationError):
    pass


class UnauthorizedError(SFMShopException):
    pass


class ForbiddenError(SFMShopException):
    pass


class BusinessLogicError(SFMShopException):
    pass


class InsufficientStockError(BusinessLogicError):
    pass



class ServiceUnavailableError(SFMShopException):
    pass


class LLMUnavailableError(ServiceUnavailableError):
    pass


class EventLogUnavailableError(ServiceUnavailableError):
    pass
