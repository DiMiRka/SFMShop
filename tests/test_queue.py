import json
from contextlib import asynccontextmanager
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.schemas import OrderCreate, OrderItemBase, ProductUpdate, UserUpdatePatch
from src.services import queue_producer
from src.services.order_service import OrderService
from src.services.product_service import ProductService
from src.services.queue_consumer import QueueConsumer
from src.services.queue_producer import QueueProducer
from src.services.user_service import UserService
from tests.test_services import FakeCache, FakeQueue, OrderRepoFake, ProductRepoFake, UserRepoFake


pytestmark = pytest.mark.anyio


class FakeMessage:
    def __init__(self, routing_key, body, retries=0):
        self.routing_key = routing_key
        self.body = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.headers = {"x-death": [{"count": retries}]} if retries else None
        self.reject = AsyncMock()

    @asynccontextmanager
    async def process(self, requeue=False):
        yield


def build_consumer():
    cache = MagicMock()
    cache.delete_users = AsyncMock()
    cache.delete_products = AsyncMock()
    cache.delete_orders = AsyncMock()
    consumer = QueueConsumer(cache, "amqp://test")
    consumer.channel = SimpleNamespace(default_exchange=SimpleNamespace(publish=AsyncMock()))
    return consumer, cache


async def deliver(consumer, queue):
    _, routing_key, payload = queue.events[-1]
    await consumer.process_cache_event(FakeMessage(routing_key, payload))
    return routing_key


async def test_user_update_event_invalidates_that_users_cache():
    queue = FakeQueue()
    users = UserRepoFake()
    await UserService(users, OrderRepoFake(), FakeCache(), queue).update_user(1, UserUpdatePatch(name="New"))
    consumer, cache = build_consumer()

    assert await deliver(consumer, queue) == "user.updated"

    cache.delete_users.assert_awaited_once_with(1)
    cache.delete_orders.assert_not_awaited()


async def test_user_delete_event_invalidates_users_orders_and_products():
    queue = FakeQueue()
    await UserService(UserRepoFake(), OrderRepoFake(), FakeCache(), queue).delete_user(1)
    consumer, cache = build_consumer()

    assert await deliver(consumer, queue) == "user.deleted"

    cache.delete_users.assert_awaited_once_with(1)
    cache.delete_orders.assert_awaited_once_with(1, [7])
    cache.delete_products.assert_awaited_once_with([1])


async def test_order_created_event_invalidates_buyer_order_and_products():
    queue = FakeQueue()
    order = OrderCreate(items=[OrderItemBase(product_id=1, quantity=1)])
    await OrderService(OrderRepoFake(), UserRepoFake(), ProductRepoFake(), FakeCache(), queue).create_order(1, order)
    consumer, cache = build_consumer()

    assert await deliver(consumer, queue) == "order.created"

    cache.delete_users.assert_awaited_once_with(1)
    cache.delete_orders.assert_awaited_once_with(1, 77)
    cache.delete_products.assert_awaited_once_with([1])


async def test_product_update_event_invalidates_that_product():
    queue = FakeQueue()
    await ProductService(ProductRepoFake(), FakeCache(), queue).update_product(1, ProductUpdate(price=Decimal("5.00")))
    consumer, cache = build_consumer()

    assert await deliver(consumer, queue) == "product.updated"

    cache.delete_products.assert_awaited_once_with(1)
    cache.delete_users.assert_not_awaited()


@pytest.mark.parametrize("method, queue_name", [
    ("process_cache_event", "cache_queue"),
    ("process_notification", "notification_queue"),
])
async def test_broken_message_is_retried_then_moved_to_error_queue(method, queue_name):
    consumer, _ = build_consumer()
    error_exchange = consumer.channel.default_exchange

    retried = FakeMessage("order.created", b"not json", retries=1)
    await getattr(consumer, method)(retried)
    retried.reject.assert_awaited_once_with(requeue=False)
    error_exchange.publish.assert_not_awaited()

    exhausted = FakeMessage("order.created", b"not json", retries=consumer.max_retries)
    await getattr(consumer, method)(exhausted)
    exhausted.reject.assert_not_awaited()
    error_exchange.publish.assert_awaited_once()
    assert error_exchange.publish.await_args.kwargs["routing_key"] == f"{queue_name}.error"


async def test_notification_uses_order_id_from_order_created_event(log_messages):
    queue = FakeQueue()
    order = OrderCreate(items=[OrderItemBase(product_id=1, quantity=1)])
    await OrderService(OrderRepoFake(), UserRepoFake(), ProductRepoFake(), FakeCache(), queue).create_order(1, order)
    consumer, _ = build_consumer()
    _, routing_key, payload = queue.events[-1]

    await consumer.process_notification(FakeMessage(routing_key, payload))

    assert "Отправка email для заказа 77" in log_messages


def build_producer(monkeypatch, publish_side_effect):
    sleeps = []

    async def fake_sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr(queue_producer.asyncio, "sleep", fake_sleep)
    producer = QueueProducer("amqp://test", max_retries=3, base_delay=0.5, backoff_multiplier=2)
    producer.connection = SimpleNamespace(is_closed=False)
    producer.exchanges["order_exchange"] = SimpleNamespace(publish=AsyncMock(side_effect=publish_side_effect))
    producer._connect = AsyncMock()
    return producer, sleeps


async def test_publish_retries_with_backoff_and_reconnects(monkeypatch):
    producer, sleeps = build_producer(monkeypatch, [ConnectionError("down"), ConnectionError("down"), None])

    assert await producer.publish_event("order_exchange", "order.created", {"order_ids": 1}) is True

    assert sleeps == [0.5, 1.0]
    assert producer._connect.await_count == 2
    message = producer.exchanges["order_exchange"].publish.await_args.args[0]
    assert json.loads(message.body) == {"order_ids": 1}


async def test_publish_gives_up_without_raising_and_logs_event(monkeypatch, log_messages):
    producer, sleeps = build_producer(monkeypatch, ConnectionError("down"))

    assert await producer.publish_event("order_exchange", "order.created", {"order_ids": 5}) is False

    assert producer.exchanges["order_exchange"].publish.await_count == 3
    assert sleeps == [0.5, 1.0]
    assert any(m.startswith("event_publish_failed") and "'order_ids': 5" in m for m in log_messages)


async def test_unknown_exchange_is_a_programming_error(monkeypatch):
    producer, _ = build_producer(monkeypatch, None)

    with pytest.raises(ValueError):
        await producer.publish_event("missing_exchange", "key", {})


async def test_order_is_created_when_rabbitmq_is_down(monkeypatch):
    async def rabbitmq_down(url):
        raise ConnectionError("rabbitmq is down")

    async def no_sleep(delay):
        return None

    monkeypatch.setattr(queue_producer.aio_pika, "connect_robust", rabbitmq_down)
    monkeypatch.setattr(queue_producer.asyncio, "sleep", no_sleep)
    producer = QueueProducer("amqp://test", max_retries=3)
    assert await producer._connect() is False

    orders = OrderRepoFake()
    users = UserRepoFake()
    service = OrderService(orders, users, ProductRepoFake(), FakeCache(), producer)
    order = OrderCreate(items=[OrderItemBase(product_id=1, quantity=1)])

    created = await service.create_order(1, order)

    assert created["order_id"] == 77
    assert users.user.balance == Decimal("90.00")


async def test_publish_reconnects_when_connection_is_closed(monkeypatch):
    producer, _ = build_producer(monkeypatch, None)
    producer.connection = SimpleNamespace(is_closed=True)

    await producer.publish_event("order_exchange", "order.created", {})

    producer._connect.assert_awaited_once()


async def test_get_instance_connects_once_and_reuses_producer(monkeypatch):
    connect = AsyncMock()
    monkeypatch.setattr(QueueProducer, "_instance", None)
    monkeypatch.setattr(QueueProducer, "_connect", connect)

    first = await QueueProducer.get_instance("amqp://test")
    second = await QueueProducer.get_instance("amqp://test")

    assert first is second
    connect.assert_awaited_once()
