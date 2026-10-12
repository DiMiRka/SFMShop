from enum import StrEnum

from sfmshop.core.exceptions import InvalidOrderStatusError


class OrderStatus(StrEnum):
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    CANCELLED = "cancelled"


ORDER_TRANSITIONS: dict[OrderStatus, frozenset[OrderStatus]] = {
    OrderStatus.PENDING: frozenset({OrderStatus.PAID, OrderStatus.FAILED, OrderStatus.CANCELLED}),
    OrderStatus.FAILED: frozenset({OrderStatus.PAID, OrderStatus.FAILED, OrderStatus.CANCELLED}),
    OrderStatus.PAID: frozenset(),
    OrderStatus.CANCELLED: frozenset(),
}

_ACTIONS = {
    OrderStatus.PAID: "оплатить",
    OrderStatus.FAILED: "оплатить",
    OrderStatus.CANCELLED: "отменить",
}


def can_transition(current: str, target: OrderStatus) -> bool:
    return target in ORDER_TRANSITIONS[OrderStatus(current)]


def ensure_transition(current: str, target: OrderStatus) -> None:
    if not can_transition(current, target):
        raise InvalidOrderStatusError(f"Нельзя {_ACTIONS[target]} заказ в статусе {current}")
