from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from sfmshop.api.main import sfmshop_app as app
from sfmshop.core import dependencies
from sfmshop.core.exceptions import InvalidOrderStatusError
from sfmshop.core.order_status import OrderStatus, ensure_transition
from sfmshop.schemas import OrderCreate, OrderItemBase
from sfmshop.services.order_service import OrderService
from tests.test_services import ACTOR, FakeCache, FakePayments, FakeQueue, OrderRepoFake, ProductRepoFake, UserRepoFake


pytestmark = pytest.mark.anyio

ALLOWED = {
    (OrderStatus.PENDING, OrderStatus.PAID),
    (OrderStatus.PENDING, OrderStatus.FAILED),
    (OrderStatus.PENDING, OrderStatus.CANCELLED),
    (OrderStatus.FAILED, OrderStatus.PAID),
    (OrderStatus.FAILED, OrderStatus.FAILED),
    (OrderStatus.FAILED, OrderStatus.CANCELLED),
}


@pytest.mark.parametrize("current", list(OrderStatus))
@pytest.mark.parametrize("target", [OrderStatus.PAID, OrderStatus.FAILED, OrderStatus.CANCELLED])
def test_only_listed_transitions_are_allowed(current, target):
    if (current, target) in ALLOWED:
        ensure_transition(current.value, target)
    else:
        with pytest.raises(InvalidOrderStatusError):
            ensure_transition(current.value, target)


def build(balance="100.00"):
    orders, products, queue = OrderRepoFake(), ProductRepoFake(), FakeQueue()
    payments = FakePayments(balance=Decimal(balance))
    service = OrderService(orders, UserRepoFake(), products, FakeCache(), queue, payments)
    return service, orders, payments, products, queue


def routing_keys(queue):
    return [event[1] for event in queue.events]


async def test_failed_payment_can_be_retried_after_top_up():
    service, orders, payments, products, queue = build(balance="5.00")

    created = await service.create_order(1, OrderCreate(items=[OrderItemBase(product_id=1, quantity=2)]), actor=ACTOR)

    assert created["status"] == "failed"
    assert payments.balances[1] == Decimal("5.00")
    assert products.product.quantity == 3

    payments.balances[1] = Decimal("25.00")
    paid = await service.pay_order(77, 1, actor=ACTOR)

    assert paid["status"] == "paid"
    assert payments.balances[1] == Decimal("5.00")
    assert orders.orders[77].payment_id == 502
    assert routing_keys(queue) == ["order.created", "order.payment_failed", "order.paid"]
    assert queue.events[-1][2] == {"order_ids": 77, "user_ids": 1, "product_ids": [1], "actor_id": 1, "actor_role": "user"}


async def test_paid_order_cannot_be_paid_again():
    service, orders, payments, _, queue = build()

    with pytest.raises(InvalidOrderStatusError, match="оплатить"):
        await service.pay_order(7, 1, actor=ACTOR)

    assert payments.balances[1] == Decimal("100.00")
    assert len(payments.payments) == 1
    assert queue.events == []


@pytest.mark.parametrize("status", [OrderStatus.PENDING, OrderStatus.FAILED])
async def test_unpaid_order_cancel_returns_stock_once(status):
    service, orders, payments, products, queue = build()
    orders.order.status = status

    cancelled = await service.cancel_order(7, 1, actor=ACTOR)

    assert cancelled["status"] == "cancelled"
    assert products.product.quantity == 7
    assert payments.balances[1] == Decimal("100.00")
    assert queue.events == [("order_exchange", "order.cancelled", {"order_ids": 7, "user_ids": 1, "product_ids": [1],
                                                                    "actor_id": 1, "actor_role": "user"})]

    with pytest.raises(InvalidOrderStatusError):
        await service.cancel_order(7, 1, actor=ACTOR)
    with pytest.raises(InvalidOrderStatusError):
        await service.pay_order(7, 1, actor=ACTOR)
    assert products.product.quantity == 7


async def test_paid_order_cannot_be_cancelled():
    service, orders, _, products, queue = build()

    with pytest.raises(InvalidOrderStatusError, match="отменить"):
        await service.cancel_order(7, 1, actor=ACTOR)

    assert orders.order.status == OrderStatus.PAID
    assert products.product.quantity == 5
    assert queue.events == []


@pytest.mark.parametrize("status, quantity_after", [
    (OrderStatus.FAILED, 7),
    (OrderStatus.CANCELLED, 5),
])
async def test_admin_delete_refunds_only_paid_and_returns_stock_only_if_reserved(status, quantity_after):
    service, orders, payments, products, _ = build()
    orders.order.status = status

    await service.delete_order(7, actor=ACTOR)

    assert orders.deleted is orders.order
    assert payments.refunds == [] and payments.top_ups == {}
    assert products.product.quantity == quantity_after


def test_invalid_transition_is_409_over_http():
    service, *_ = build()

    async def override_order_service():
        return service

    async def override_current_user():
        return SimpleNamespace(id=1, is_admin=False)

    app.dependency_overrides[dependencies.get_current_user] = override_current_user
    app.dependency_overrides[dependencies.get_order_write_service] = override_order_service
    try:
        response = TestClient(app).post("/v1/orders/7/pay")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert response.json() == {"detail": "Нельзя оплатить заказ в статусе paid"}


class ChangingPayments(FakePayments):
    def __init__(self, change):
        super().__init__()
        self.change = change

    async def charge(self, order_id, user_id, amount):
        result = await super().charge(order_id, user_id, amount)
        self.change()
        return result


@pytest.mark.parametrize("change", ["cancel", "delete"])
async def test_money_is_refunded_when_order_changes_during_payment(change):
    orders, products, queue = OrderRepoFake(), ProductRepoFake(), FakeQueue()
    orders.order.status = OrderStatus.PENDING
    orders.order.payment_id = None

    def concurrent_change():
        if change == "cancel":
            orders.order.status = OrderStatus.CANCELLED
        else:
            del orders.orders[7]

    payments = ChangingPayments(concurrent_change)
    payments.payments.clear()
    service = OrderService(orders, UserRepoFake(), products, FakeCache(), queue, payments)

    with pytest.raises(InvalidOrderStatusError, match="изменился"):
        await service.pay_order(7, 1, actor=ACTOR)

    assert payments.refunds == [500]
    assert payments.balances[1] == Decimal("100.00")
    assert orders.order.payment_id is None
    assert queue.events == []


async def test_payment_already_recorded_by_parallel_request_is_returned_without_new_event():
    orders, queue = OrderRepoFake(), FakeQueue()
    orders.order.status = OrderStatus.PENDING

    def parallel_request_recorded_it():
        orders.order.status = OrderStatus.PAID

    payments = ChangingPayments(parallel_request_recorded_it)
    service = OrderService(orders, UserRepoFake(), ProductRepoFake(), FakeCache(), queue, payments)

    result = await service.pay_order(7, 1, actor=ACTOR)

    assert result["status"] == "paid"
    assert payments.refunds == []
    assert queue.events == []


async def test_failed_payment_is_not_refunded_when_order_changes():
    orders = OrderRepoFake()
    orders.order.status = OrderStatus.PENDING

    def cancel():
        orders.order.status = OrderStatus.CANCELLED

    payments = ChangingPayments(cancel)
    payments.payments.clear()
    payments.balances[1] = Decimal("0.00")
    service = OrderService(orders, UserRepoFake(), ProductRepoFake(), FakeCache(), FakeQueue(), payments)

    with pytest.raises(InvalidOrderStatusError):
        await service.pay_order(7, 1, actor=ACTOR)

    assert payments.refunds == []


async def test_delete_is_aborted_when_order_changes_after_refund():
    service, orders, payments, products, _ = build()
    original_refund = payments.refund

    async def refund_then_change(payment_id):
        await original_refund(payment_id)
        orders.order.status = OrderStatus.CANCELLED

    payments.refund = refund_then_change

    with pytest.raises(InvalidOrderStatusError, match="изменился"):
        await service.delete_order(7, actor=ACTOR)

    assert orders.deleted is None
    assert products.product.quantity == 5
