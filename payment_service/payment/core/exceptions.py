class PaymentServiceError(Exception):
    pass


class NotFoundError(PaymentServiceError):
    pass


class ConflictError(PaymentServiceError):
    pass


class IdempotencyKeyReusedError(PaymentServiceError):
    pass
