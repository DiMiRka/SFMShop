from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.models.exceptions import ValidationError
from src.schemas import OrderCreate, OrderItemBase
from src.services.order_service import OrderService


pytestmark = pytest.mark.anyio


class BeginContext:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


def build_service():
    order_rep = MagicMock()
    order_rep.db.begin.return_value = BeginContext()
    order_rep.create = AsyncMock(return_value=42)
    order_rep.create_order_item = AsyncMock()

    user_rep = MagicMock()
    user_rep.get_by_id_for_update = AsyncMock(
        return_value=MagicMock(id=1, balance=Decimal("1000.00"))
    )

    product = MagicMock(id=2, price=Decimal("300.00"), quantity=5)
    product_rep = MagicMock()
    product_rep.get_by_ids_for_update = AsyncMock(return_value=[product])

    cache = MagicMock()
    queue = MagicMock()
    queue.publish_event = AsyncMock(return_value=True)

    service = OrderService(
        order_rep=order_rep,
        user_rep=user_rep,
        product_rep=product_rep,
        cache=cache,
        queue=queue,
    )
    return service, order_rep, user_rep, product_rep, queue


async def test_order_service_create_order_happy_path_with_mocks():
    service, order_rep, user_rep, product_rep, queue = build_service()
    order = OrderCreate(user_id=1, items=[OrderItemBase(product_id=2, quantity=1)])

    result = await service.create_order(order)

    assert result["order_id"] == 42
    assert result["total"] == 300.0
    user_rep.get_by_id_for_update.assert_awaited_once_with(1)
    product_rep.get_by_ids_for_update.assert_awaited_once_with([2])
    order_rep.create.assert_awaited_once()
    order_rep.create_order_item.assert_awaited_once()
    queue.publish_event.assert_awaited_once()


async def test_order_service_empty_order_raises_and_dependencies_not_called():
    """empty_raises: DB and notification are not called."""
    service, order_rep, user_rep, product_rep, queue = build_service()
    order = OrderCreate(user_id=1, items=[])

    with pytest.raises(ValidationError):
        await service.create_order(order)

    user_rep.get_by_id_for_update.assert_not_awaited()
    product_rep.get_by_ids_for_update.assert_not_awaited()
    order_rep.create.assert_not_awaited()
    queue.publish_event.assert_not_awaited()


async def test_order_service_db_failure_does_not_send_notification():
    service, order_rep, user_rep, product_rep, queue = build_service()
    order_rep.create.side_effect = RuntimeError("DB error")
    order = OrderCreate(user_id=1, items=[OrderItemBase(product_id=2, quantity=1)])

    with pytest.raises(RuntimeError, match="DB error"):
        await service.create_order(order)

    order_rep.create.assert_awaited_once()
    queue.publish_event.assert_not_awaited()
