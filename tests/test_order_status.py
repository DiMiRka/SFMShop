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
from tests.test_services import FakeCache, FakeQueue, OrderRepoFake, ProductRepoFake, UserRepoFake


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


def build():
    orders, users, products, queue = OrderRepoFake(), UserRepoFake(), ProductRepoFake(), FakeQueue()
    return OrderService(orders, users, products, FakeCache(), queue), orders, users, products, queue


def routing_keys(queue):
    return [event[1] for event in queue.events]


async def test_failed_payment_can_be_retried_after_top_up():
    service, orders, users, products, queue = build()
    users.user.balance = Decimal("5.00")

    created = await service.create_order(1, OrderCreate(items=[OrderItemBase(product_id=1, quantity=2)]))

    assert created["status"] == "failed"
    assert users.user.balance == Decimal("5.00")
    assert products.product.quantity == 3

    users.user.balance = Decimal("25.00")
    paid = await service.pay_order(77, 1)

    assert paid["status"] == "paid"
    assert users.user.balance == Decimal("5.00")
    assert routing_keys(queue) == ["order.created", "order.payment_failed", "order.paid"]
    assert queue.events[-1][2] == {"order_ids": 77, "user_ids": 1, "product_ids": [1]}


async def test_paid_order_cannot_be_paid_again():
    service, orders, users, _, queue = build()

    with pytest.raises(InvalidOrderStatusError, match="оплатить"):
        await service.pay_order(7, 1)

    assert users.user.balance == Decimal("100.00")
    assert queue.events == []


@pytest.mark.parametrize("status", [OrderStatus.PENDING, OrderStatus.FAILED])
async def test_unpaid_order_cancel_returns_stock_once(status):
    service, orders, users, products, queue = build()
    orders.order.status = status

    cancelled = await service.cancel_order(7, 1)

    assert cancelled["status"] == "cancelled"
    assert products.product.quantity == 7
    assert users.user.balance == Decimal("100.00")
    assert queue.events == [("order_exchange", "order.cancelled", {"order_ids": 7, "user_ids": 1, "product_ids": [1]})]

    with pytest.raises(InvalidOrderStatusError):
        await service.cancel_order(7, 1)
    with pytest.raises(InvalidOrderStatusError):
        await service.pay_order(7, 1)
    assert products.product.quantity == 7


async def test_paid_order_cannot_be_cancelled():
    service, orders, _, products, queue = build()

    with pytest.raises(InvalidOrderStatusError, match="отменить"):
        await service.cancel_order(7, 1)

    assert orders.order.status == OrderStatus.PAID
    assert products.product.quantity == 5
    assert queue.events == []


@pytest.mark.parametrize("status, quantity_after", [
    (OrderStatus.FAILED, 7),
    (OrderStatus.CANCELLED, 5),
])
async def test_admin_delete_refunds_only_paid_and_returns_stock_only_if_reserved(status, quantity_after):
    service, orders, users, products, _ = build()
    orders.order.status = status

    await service.delete_order(7)

    assert orders.deleted is orders.order
    assert users.updated is None
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
