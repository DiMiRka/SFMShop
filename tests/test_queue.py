import json
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from aio_pika.exceptions import MessageProcessError
from aio_pika.message import ProcessContext

from sfmshop.schemas import OrderCreate, OrderItemBase, ProductCreate, ProductUpdate, UserCreate, UserUpdatePatch
from sfmshop.services import queue_producer
from sfmshop.services.order_service import OrderService
from sfmshop.services.product_service import ProductService
from sfmshop.services.queue_consumer import QueueConsumer
from sfmshop.services.queue_producer import QueueProducer
from sfmshop.services.user_service import UserService
from tests.test_services import FakeCache, FakeQueue, OrderRepoFake, ProductRepoFake, UserRepoFake


pytestmark = pytest.mark.anyio


class FakeMessage:
    def __init__(self, routing_key, body, retries=0):
        self.routing_key = routing_key
        self.body = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.headers = {"x-death": [{"count": retries}]} if retries else None
        self.redelivered = False
        self.channel = SimpleNamespace(is_closed=False)
        self.processed = False
        self.ack = AsyncMock(side_effect=self.settle)
        self.reject = AsyncMock(side_effect=self.settle)

    async def settle(self, *args, **kwargs):
        if self.processed:
            raise MessageProcessError("Message already processed", self)
        self.processed = True

    def process(self, requeue=False, reject_on_redelivered=False, ignore_processed=False):
        return ProcessContext(
            self,
            requeue=requeue,
            reject_on_redelivered=reject_on_redelivered,
            ignore_processed=ignore_processed,
        )


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
    retried.ack.assert_not_awaited()
    error_exchange.publish.assert_not_awaited()

    exhausted = FakeMessage("order.created", b"not json", retries=consumer.max_retries)
    await getattr(consumer, method)(exhausted)
    exhausted.reject.assert_not_awaited()
    exhausted.ack.assert_awaited_once()
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


class TransactionLog:
    def __init__(self):
        self.entries = []

    def begin(self):
        log = self

        class Transaction:
            async def __aenter__(self):
                log.entries.append("begin")

            async def __aexit__(self, exc_type, exc, tb):
                log.entries.append("commit" if exc_type is None else "rollback")
                return False

        return Transaction()

    async def publish_event(self, exchange, routing_key, message):
        self.entries.append(f"publish {routing_key}")
        return True


def services_on(log):
    products, users, orders = ProductRepoFake(), UserRepoFake(), OrderRepoFake()
    for repo in (products, users, orders):
        repo.db = log
    return (
        ProductService(products, FakeCache(), log),
        UserService(users, orders, FakeCache(), log),
        OrderService(orders, users, products, FakeCache(), log),
    )


@pytest.mark.parametrize("routing_key, operation", [
    ("product.created", lambda p, u, o: p.create_product(ProductCreate(name="Desk", price=Decimal("10.00"), quantity=1))),
    ("product.updated", lambda p, u, o: p.update_product(1, ProductUpdate(quantity=2))),
    ("product.deleted", lambda p, u, o: p.delete_product(1)),
    ("user.created", lambda p, u, o: u.register_user(
        UserCreate(name="New", email="new@test.com", age=20, password="abc12345"))),
    ("user.updated", lambda p, u, o: u.update_user(1, UserUpdatePatch(name="Changed"))),
    ("user.deleted", lambda p, u, o: u.delete_user(1)),
    ("order.created", lambda p, u, o: o.create_order(1, OrderCreate(items=[OrderItemBase(product_id=1, quantity=1)]))),
    ("order.deleted", lambda p, u, o: o.delete_order(7, 1)),
])
async def test_event_is_published_only_after_commit(routing_key, operation):
    log = TransactionLog()

    await operation(*services_on(log))

    assert log.entries == ["begin", "commit", f"publish {routing_key}"]


@pytest.mark.parametrize("connection, should_close", [
    (None, False),
    (SimpleNamespace(is_closed=True, close=AsyncMock()), False),
    (SimpleNamespace(is_closed=False, close=AsyncMock()), True),
])
async def test_consumer_closes_open_connection_on_shutdown(connection, should_close):
    consumer, _ = build_consumer()
    consumer.connection = connection

    await consumer.close()

    if connection is not None:
        assert connection.close.await_count == (1 if should_close else 0)


def scripted_connect(consumer, results):
    attempts = []

    async def connect():
        ok = results[min(len(attempts), len(results) - 1)]
        attempts.append(ok)
        consumer.connection = SimpleNamespace(is_closed=False, close=AsyncMock()) if ok else None
        return ok

    consumer._connect = connect
    return attempts


async def test_consumer_keeps_reconnecting_with_backoff_until_rabbitmq_is_up(monkeypatch, log_messages):
    delays = []

    async def fake_sleep(delay):
        delays.append(delay)

    monkeypatch.setattr("sfmshop.services.queue_consumer.asyncio.sleep", fake_sleep)
    consumer = QueueConsumer(MagicMock(), "amqp://test", reconnect_base_delay=1, reconnect_max_delay=3)
    attempts = scripted_connect(consumer, [False, False, False, False, True])

    await consumer.start()
    assert not consumer.is_connected
    assert "Consumer started" not in log_messages

    await consumer._reconnect_task

    assert attempts == [False, False, False, False, True]
    assert delays == [1, 2, 3, 3]
    assert consumer.is_connected
    assert "Consumer started" in log_messages


async def test_consumer_connected_at_start_needs_no_background_task():
    consumer = QueueConsumer(MagicMock(), "amqp://test")
    scripted_connect(consumer, [True])

    await consumer.start()

    assert consumer.is_connected and consumer._reconnect_task is None


async def test_close_stops_pending_reconnect_loop():
    consumer = QueueConsumer(MagicMock(), "amqp://test", reconnect_base_delay=60)
    scripted_connect(consumer, [False])

    await consumer.start()
    task = consumer._reconnect_task
    await consumer.close()

    assert task.cancelled()


async def test_failed_setup_closes_half_open_connection(monkeypatch):
    connection = SimpleNamespace(is_closed=False, close=AsyncMock(),
                                 channel=AsyncMock(side_effect=ConnectionError("channel failed")))

    async def connect_robust(url):
        return connection

    monkeypatch.setattr("sfmshop.services.queue_consumer.aio_pika.connect_robust", connect_robust)
    consumer = QueueConsumer(MagicMock(), "amqp://test")

    assert await consumer._connect() is False

    connection.close.assert_awaited_once()
    assert consumer.connection is None and not consumer.is_connected


async def test_disconnected_consumer_degrades_readiness():
    from sfmshop.services.health_service import HealthService

    async def ok():
        return True

    queue = SimpleNamespace(ensure_connected=AsyncMock(return_value=True))
    consumer = QueueConsumer(MagicMock(), "amqp://test")

    result = await HealthService({}, SimpleNamespace(ping=ok), queue, consumer=consumer).readiness()

    assert result["status"] == "degraded"
    assert result["checks"]["queue_consumer"] == "fail"


async def test_producer_reconnects_on_demand_for_readiness(monkeypatch):
    producer = QueueProducer("amqp://test")
    producer.connection = None

    async def connect():
        producer.connection = SimpleNamespace(is_closed=False)
        return True

    producer._connect = connect

    assert await producer.ensure_connected() is True

    async def still_down():
        return False

    producer.connection = SimpleNamespace(is_closed=True)
    producer._connect = still_down
    assert await producer.ensure_connected() is False
