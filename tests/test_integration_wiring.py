from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest


pytestmark = pytest.mark.anyio


class FakeCache:
    def __init__(self):
        self.deleted = []

    async def get_or_set_cache(self, key, func, ttl=900):
        self.last_key = key
        return await func()

    async def delete_users(self, user_id):
        self.deleted.append(("users", user_id))

    async def delete_products(self, product_ids):
        self.deleted.append(("products", product_ids))

    async def delete_orders(self, user_ids, order_ids):
        self.deleted.append(("orders", user_ids, order_ids))


class ScalarResult:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class QueryResult:
    def __init__(self, values=None, scalar=None, one=None):
        self.values = values or []
        self._scalar = scalar
        self._one = one

    def scalars(self):
        return ScalarResult(self.values)

    def all(self):
        return self.values

    def scalar_one_or_none(self):
        return self._scalar

    def scalar(self):
        return self._scalar

    def one(self):
        return self._one


class SequenceDb:
    def __init__(self, *results):
        self.results = list(results)
        self.executed = []

    async def execute(self, query):
        self.executed.append(query)
        return self.results.pop(0)


async def test_database_query_helpers_use_cache_and_shape_data(monkeypatch):
    from src.database import queries

    cache = FakeCache()
    monkeypatch.setattr(queries, "cache", cache)

    product = SimpleNamespace(id=1, name="Mouse", price=Decimal("10.00"), quantity=2, created_at=datetime(2026, 1, 1))
    item = SimpleNamespace(product=product, product_id=1, quantity=2, price=Decimal("10.00"))
    order = SimpleNamespace(id=5, user_id=1, total=Decimal("20.00"), created_at=SimpleNamespace(isoformat=lambda: "date"), items=[item])

    assert await queries.get_orders_with_products(SequenceDb(QueryResult([order])), 1) == [
        {"order_id": 5, "product": "Mouse", "quantity": 2, "price": Decimal("10.00")}
    ]

    row = SimpleNamespace(id=1, name="Dima", orders_count=3)
    assert await queries.get_orders_count_by_users(SequenceDb(QueryResult([row]))) == [
        {"user_id": 1, "name": "Dima", "orders_count": 3}
    ]

    assert (await queries.get_products_sorted_by_price(SequenceDb(QueryResult([product]))))[0]["name"] == "Mouse"

    history_row = SimpleNamespace(
        order_id=5,
        created_at=SimpleNamespace(isoformat=lambda: "date"),
        product_name="Mouse",
        product_price=Decimal("10.00"),
        order_quantity=2,
    )
    assert await queries.get_user_order_history(SequenceDb(QueryResult([history_row])), 1) == [
        {"order_id": 5, "created_at": "date", "product_name": "Mouse", "product_price": 10.0, "quantity": 2}
    ]

    stats_row = SimpleNamespace(id=1, name="Dima", order_count=2, total_amount=Decimal("50.00"))
    assert await queries.get_order_statistics(SequenceDb(QueryResult([stats_row]))) == [
        {"user_id": 1, "name": "Dima", "order_count": 2, "total_amount": 50.0}
    ]

    top_row = SimpleNamespace(id=1, name="Mouse", total_sold=4)
    assert await queries.get_top_products(SequenceDb(QueryResult([top_row])), limit=1) == [
        {"id": 1, "name": "Mouse", "total_sold": 4}
    ]

    assert await queries.generate_sales_report(
        SequenceDb(QueryResult(), QueryResult(scalar=Decimal("100.00")), QueryResult(scalar=2)),
        "2026-01-01",
    ) == {"total": Decimal("100.00"), "count": 2}

    assert await queries.calculate_total_revenue(
        SequenceDb(QueryResult(one=(Decimal("100.00"), 2))),
        "2026-01-01",
        "2026-01-31",
    ) == {"total": Decimal("100.00"), "count": 2, "average": 50.0}


async def test_dependency_factories_and_current_user(monkeypatch):
    from src.core import dependencies as deps

    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(redis="redis", cache="cache", queue="queue", http_client="http")))
    assert deps.get_redis(request) == "redis"
    assert deps.get_cache(request) == "cache"
    assert deps.get_queue(request) == "queue"
    assert deps.get_http_client(request) == "http"

    db = object()
    assert (await deps.get_product_write_repository(db)).db is db
    assert (await deps.get_product_read_repository(db)).db is db
    assert (await deps.get_order_write_repository(db)).db is db
    assert (await deps.get_order_read_repository(db)).db is db
    assert (await deps.get_user_write_repository(db)).db is db
    assert (await deps.get_user_read_repository(db)).db is db

    product_service = await deps.get_product_write_service("product-rep", "cache", "queue")
    assert product_service.product_rep == "product-rep"
    user_service = await deps.get_user_write_service("user-rep", "order-rep", "cache", "queue")
    assert user_service.user_rep == "user-rep"
    order_service = await deps.get_order_write_service("order-rep", "user-rep", "product-rep", "cache", "queue")
    assert order_service.order_rep == "order-rep"

    user = SimpleNamespace(id=7)
    monkeypatch.setattr(deps, "decode_token", lambda token: async_value({"sub": "7"}))
    current = await deps.get_current_user(SequenceDb(QueryResult(scalar=user)), token="token")
    assert current is user

    monkeypatch.setattr(deps, "decode_token", lambda token: async_value(None))
    with pytest.raises(Exception):
        await deps.get_current_user(SequenceDb(QueryResult(scalar=user)), token="bad")

    class Client:
        def __init__(self, *args, **kwargs):
            self.closed = False

        async def close(self):
            self.closed = True

    monkeypatch.setattr(deps, "ExchangeRateClient", Client)
    exchange_gen = deps.get_exchange_client()
    exchange_client = await anext(exchange_gen)
    assert isinstance(exchange_client, Client)
    with pytest.raises(StopAsyncIteration):
        await anext(exchange_gen)
    assert exchange_client.closed

    monkeypatch.setattr(deps, "MultiExchangeClient", Client)
    multi_gen = deps.get_multi_exchange_client()
    multi_client = await anext(multi_gen)
    assert isinstance(multi_client, Client)
    with pytest.raises(StopAsyncIteration):
        await anext(multi_gen)
    assert multi_client.closed


async def async_value(value):
    return value


async def test_database_connection_session_generators(monkeypatch):
    from src.database import connection

    class Session:
        def __init__(self):
            self.committed = False
            self.rolled_back = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def commit(self):
            self.committed = True

        async def rollback(self):
            self.rolled_back = True

    write_session = Session()
    read_session = Session()
    monkeypatch.setattr(connection, "async_session", lambda: write_session)
    monkeypatch.setattr(connection, "async_session_replica", lambda: read_session)

    write_gen = connection.get_write_session()
    assert await anext(write_gen) is write_session
    with pytest.raises(StopAsyncIteration):
        await anext(write_gen)
    assert write_session.committed

    read_gen = connection.get_read_session()
    assert await anext(read_gen) is read_session
    with pytest.raises(StopAsyncIteration):
        await anext(read_gen)


async def test_fastapi_main_lifespan_and_logging_middleware(monkeypatch):
    import src.api.main as main

    class Redis:
        async def ping(self):
            self.pinged = True

        async def close(self):
            self.closed = True

    class RedisFactory:
        @staticmethod
        def from_url(url):
            return Redis()

    class HttpClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def aclose(self):
            self.closed = True

    class Queue:
        connection = SimpleNamespace(is_closed=False)

        async def close(self):
            self.closed = True

    class QueueProducer:
        @staticmethod
        async def get_instance(url):
            return Queue()

    class Consumer:
        def __init__(self, cache, url):
            self.cache = cache
            self.url = url

        async def start(self):
            self.started = True

    monkeypatch.setattr(main, "setup_logging", lambda: None)
    monkeypatch.setattr(main.redis.asyncio, "Redis", RedisFactory)
    monkeypatch.setattr(main.httpx, "AsyncClient", HttpClient)
    monkeypatch.setattr(main, "QueueProducer", QueueProducer)
    monkeypatch.setattr(main, "QueueConsumer", Consumer)

    app = SimpleNamespace(state=SimpleNamespace())
    async with main.lifespan(app):
        assert app.state.redis.pinged
        assert app.state.http_client.timeout == 5
        assert isinstance(app.state.cache, main.CacheService)
        assert isinstance(app.state.consumer, Consumer)

    request = SimpleNamespace(method="GET", url=SimpleNamespace(path="/v1/products"))
    response = SimpleNamespace(status_code=200, headers={})

    async def call_next(req):
        return response

    assert await main.log_requests(request, call_next) is response
    assert "X-Process-Time" in response.headers


async def test_queue_producer_and_consumer_helpers(monkeypatch):
    from src.services import queue_consumer, queue_producer

    class Exchange:
        def __init__(self):
            self.published = []

        async def publish(self, message, routing_key):
            self.published.append((message.body, routing_key))

    exchange = Exchange()

    class Channel:
        def __init__(self):
            self.default_exchange = exchange

        async def declare_exchange(self, name, exchange_type, durable):
            return exchange

        async def channel(self):
            return self

    class Connection:
        is_closed = False

        async def channel(self):
            return Channel()

        async def close(self):
            self.closed = True

    async def connect_robust(url):
        return Connection()

    monkeypatch.setattr(queue_producer.aio_pika, "connect_robust", connect_robust)
    producer = queue_producer.QueueProducer("amqp://test")
    await producer._connect()
    assert "user_exchange" in producer.exchanges
    assert await producer.publish_event("user_exchange", "user.created", {"user_id": 1}) is True
    with pytest.raises(ValueError):
        await producer.publish_event("missing", "key", {})
    await producer.close()

    cache = FakeCache()
    consumer = queue_consumer.QueueConsumer(cache, "amqp://test")
    assert consumer.get_retry_count(SimpleNamespace(headers={"x-death": [{"count": 2}]})) == 2
    assert consumer.get_retry_count(SimpleNamespace(headers=None)) == 0
    await consumer.invalidate_user_cache({"user_id": 1})
    await consumer.invalidate_product_cache({"product_ids": [2]})
    await consumer.invalidate_order_cache({"user_ids": [1], "order_ids": [3]})
    assert ("users", 1) in cache.deleted

    consumer.channel = SimpleNamespace(default_exchange=exchange)
    await consumer.move_to_error_queue(SimpleNamespace(body=b"bad"), "cache_queue")
    assert exchange.published[-1][1] == "cache_queue.error"

    monkeypatch.setattr(consumer, "_setup_cache_consumer", lambda: async_value(None))
    monkeypatch.setattr(consumer, "_setup_notification_consumer", lambda: async_value(None))
    monkeypatch.setattr(queue_consumer.aio_pika, "connect_robust", connect_robust)
    await consumer._connect()
    await consumer.start()


def test_setup_logging_is_idempotent(monkeypatch):
    from src.services import log_service

    calls = []
    monkeypatch.setattr(log_service.logger, "remove", lambda: calls.append("remove"))
    monkeypatch.setattr(log_service.logger, "add", lambda *args, **kwargs: calls.append((args, kwargs)))
    monkeypatch.setattr(log_service, "_is_logging_configured", False)

    log_service.setup_logging()
    log_service.setup_logging()

    assert calls.count("remove") == 1


