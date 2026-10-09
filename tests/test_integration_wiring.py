from types import SimpleNamespace

import pytest

from sfmshop.core.exceptions import ForbiddenError


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


async def test_dependency_factories_and_current_user(monkeypatch):
    from sfmshop.core import dependencies as deps

    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(cache="cache", queue="queue")))
    assert deps.get_cache(request) == "cache"
    assert deps.get_queue(request) == "queue"

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

    user = SimpleNamespace(id=7, is_active=True)
    monkeypatch.setattr(deps, "decode_token", lambda token: async_value({"sub": "7"}))
    current = await deps.get_current_user(SequenceDb(QueryResult(scalar=user)), token="token")
    assert current is user

    inactive = SimpleNamespace(id=7, is_active=False)
    with pytest.raises(ForbiddenError):
        await deps.get_current_user(SequenceDb(QueryResult(scalar=inactive)), token="token")

    monkeypatch.setattr(deps, "decode_token", lambda token: async_value(None))
    with pytest.raises(Exception):
        await deps.get_current_user(SequenceDb(QueryResult(scalar=user)), token="bad")


async def async_value(value):
    return value


async def test_database_connection_session_generators(monkeypatch):
    from sfmshop.database import connection

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
    import sfmshop.api.main as main

    class Redis:
        async def ping(self):
            self.pinged = True

        async def close(self):
            self.closed = True

    class RedisFactory:
        @staticmethod
        def from_url(url, **kwargs):
            redis_client = Redis()
            redis_client.options = kwargs
            return redis_client

    class Queue:
        connection = SimpleNamespace(is_closed=False)

        async def close(self):
            self.closed = True

    class QueueProducer:
        @staticmethod
        async def get_instance(url, **kwargs):
            return Queue()

    class Consumer:
        def __init__(self, cache, url, events=None):
            self.cache = cache
            self.url = url
            self.events = events

        async def start(self):
            self.started = True

        async def close(self):
            self.closed = True

    monkeypatch.setattr(main, "setup_logging", lambda: None)
    metrics_ports = []
    monkeypatch.setattr(main, "start_metrics_server", metrics_ports.append)
    monkeypatch.setattr(main.redis.asyncio, "Redis", RedisFactory)
    monkeypatch.setattr(main, "QueueProducer", QueueProducer)
    monkeypatch.setattr(main, "QueueConsumer", Consumer)

    class LLMClient:
        async def close(self):
            self.closed = True

    llm_client = LLMClient()
    monkeypatch.setattr(main, "create_llm_client", lambda settings: llm_client)

    class Collection:
        def __init__(self):
            self.indexes = []

        async def create_index(self, keys, **kwargs):
            self.indexes.append((keys, kwargs))

    class MongoClient:
        def __init__(self):
            self.collection = Collection()

        def __getitem__(self, db_name):
            self.db_name = db_name
            return {"events": self.collection}

        async def close(self):
            self.closed = True

    mongo = MongoClient()
    monkeypatch.setattr(main, "create_mongo_client", lambda url: mongo)

    app = SimpleNamespace(state=SimpleNamespace())
    async with main.lifespan(app):
        assert app.state.redis.pinged
        assert app.state.redis.options["socket_connect_timeout"] <= 1
        assert isinstance(app.state.cache, main.CacheService)
        assert isinstance(app.state.consumer, Consumer)
        assert app.state.llm_client is llm_client
        assert app.state.consumer.events is app.state.events
        assert mongo.db_name == main.app_settings.mongo_db
        ttl_index = mongo.collection.indexes[0]
        assert ttl_index[1]["expireAfterSeconds"] == main.app_settings.event_log_ttl_days * 86400

    assert llm_client.closed
    assert mongo.closed
    assert app.state.consumer.closed

    async def mongo_down(keys, **kwargs):
        raise ConnectionError("mongo is down")

    mongo.collection.create_index = mongo_down

    async def redis_down(self):
        raise main.redis.exceptions.ConnectionError("redis is down")

    monkeypatch.setattr(Redis, "ping", redis_down)
    async with main.lifespan(SimpleNamespace(state=SimpleNamespace())):
        pass

    assert metrics_ports == [main.app_settings.metrics_port, main.app_settings.metrics_port]

    request = SimpleNamespace(method="GET", url=SimpleNamespace(path="/v1/products"), scope={})
    response = SimpleNamespace(status_code=200, headers={})

    async def call_next(req):
        return response

    assert await main.log_requests(request, call_next) is response
    assert "X-Process-Time" in response.headers


async def test_queue_producer_and_consumer_helpers(monkeypatch):
    from sfmshop.services import queue_consumer, queue_producer

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
    await consumer.invalidate_user_cache({"user_ids": 1})
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
    from sfmshop.services import log_service

    calls = []
    monkeypatch.setattr(log_service.logger, "remove", lambda: calls.append("remove"))
    monkeypatch.setattr(log_service.logger, "add", lambda *args, **kwargs: calls.append((args, kwargs)))
    monkeypatch.setattr(log_service, "_is_logging_configured", False)

    log_service.setup_logging()
    log_service.setup_logging()

    assert calls.count("remove") == 1


def test_logs_are_written_to_project_root_regardless_of_cwd(monkeypatch, tmp_path):
    from pathlib import Path

    from sfmshop.services import log_service

    sinks = []
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(log_service.logger, "remove", lambda: None)
    monkeypatch.setattr(log_service.logger, "add", lambda sink, **kwargs: sinks.append(sink))
    monkeypatch.setattr(log_service, "_is_logging_configured", False)

    log_service.setup_logging()

    project_logs = Path(__file__).resolve().parents[1] / "logs"
    assert {Path(sink) for sink in sinks if isinstance(sink, str)} == {
        project_logs / "app.log",
        project_logs / "errors_log.log",
    }
    assert not (tmp_path / "logs").exists()
