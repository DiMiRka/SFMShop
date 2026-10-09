from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from pymongo import DESCENDING
from pymongo.errors import ServerSelectionTimeoutError

from sfmshop.api.main import sfmshop_app as app
from sfmshop.core import dependencies
from sfmshop.core.exceptions import EventLogUnavailableError
from sfmshop.repositories.event_repository import EventRepository
from sfmshop.schemas import OrderCreate, OrderItemBase, ProductCreate, UserCreate
from sfmshop.schemas.events import EventFilter
from sfmshop.services import queue_consumer
from sfmshop.services.event_log_service import EventLogService, build_event
from sfmshop.services.health_service import HealthService
from sfmshop.services.order_service import OrderService
from sfmshop.services.product_service import ProductService
from sfmshop.services.user_service import UserService
from tests.test_queue import FakeMessage, build_consumer, build_producer
from tests.test_services import FakeCache, FakeQueue, OrderRepoFake, ProductRepoFake, UserRepoFake


OCCURRED_AT = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)


class Cursor:
    def __init__(self, collection, documents):
        self.collection = collection
        self.documents = documents

    def sort(self, key, direction):
        self.collection.sorted_by = (key, direction)
        return self

    def limit(self, limit):
        self.collection.limited_to = limit
        return self

    async def to_list(self, length):
        return self.documents[:length]


class Collection:
    def __init__(self, documents=()):
        self.documents = list(documents)
        self.updates = []
        self.indexes = []

    async def update_one(self, query, update, upsert=False):
        self.updates.append((query, update, upsert))
        if not any(doc["_id"] == query["_id"] for doc in self.documents):
            self.documents.append({"_id": query["_id"], **update["$setOnInsert"]})

    def find(self, query):
        self.query = query
        return Cursor(self, self.documents)

    async def create_index(self, keys, **kwargs):
        self.indexes.append((keys, kwargs))


def event_message(routing_key, payload, message_id="m-1"):
    message = FakeMessage(routing_key, payload)
    message.message_id = message_id
    message.timestamp = OCCURRED_AT
    return message


def test_build_event_normalizes_entity_ids():
    event = build_event("order.created", {"order_ids": 7, "user_ids": 1, "product_ids": [3, None, 4]}, "m-1",
                        OCCURRED_AT)

    assert event == {
        "_id": "m-1",
        "event": "order.created",
        "occurred_at": OCCURRED_AT,
        "product_ids": [3, 4],
        "user_ids": [1],
        "order_ids": [7],
        "payload": {"order_ids": 7, "user_ids": 1, "product_ids": [3, None, 4]},
    }
    assert build_event("product.created", {})["_id"]


@pytest.mark.anyio
@pytest.mark.parametrize("operation, routing_key, ids", [
    (lambda q: ProductService(ProductRepoFake(), FakeCache(), q).create_product(
        ProductCreate(name="Desk", price=Decimal("10.00"), quantity=1)),
     "product.created", {"product_ids": [44], "user_ids": [], "order_ids": []}),
    (lambda q: UserService(UserRepoFake(), OrderRepoFake(), FakeCache(), q).register_user(
        UserCreate(name="New", email="new@test.com", age=20, password="abc12345")),
     "user.created", {"product_ids": [], "user_ids": [2], "order_ids": []}),
    (lambda q: OrderService(OrderRepoFake(), UserRepoFake(), ProductRepoFake(), FakeCache(), q).create_order(
        1, OrderCreate(items=[OrderItemBase(product_id=1, quantity=1)])),
     "order.created", {"product_ids": [1], "user_ids": [1], "order_ids": [77]}),
])
async def test_service_events_are_stored_with_entity_ids(operation, routing_key, ids):
    queue = FakeQueue()
    await operation(queue)
    _, published_key, payload = next(event for event in queue.events if event[1] == routing_key)
    collection = Collection()
    consumer, _ = build_consumer()
    consumer.events = EventRepository(collection)

    message = event_message(published_key, payload)
    await consumer.process_event_log(message)

    [stored] = collection.documents
    assert stored["event"] == routing_key
    assert stored["occurred_at"] == OCCURRED_AT
    assert {key: stored[key] for key in ids} == ids
    message.ack.assert_awaited_once()


@pytest.mark.anyio
async def test_redelivered_event_is_stored_once():
    collection = Collection()
    repository = EventRepository(collection)
    event = build_event("product.updated", {"product_ids": 1}, "same-id", OCCURRED_AT)

    await repository.add(event)
    await repository.add(event)

    assert len(collection.documents) == 1
    query, update, upsert = collection.updates[0]
    assert query == {"_id": "same-id"} and upsert is True
    assert "_id" not in update["$setOnInsert"]


@pytest.mark.anyio
async def test_mongo_failure_is_retried_then_parked_with_original_routing_key():
    consumer, _ = build_consumer()
    consumer.events = SimpleNamespace(add=AsyncMock(side_effect=ServerSelectionTimeoutError("mongo down")))
    error_exchange = consumer.channel.default_exchange

    retried = event_message("order.created", {"order_ids": 1})
    await consumer.process_event_log(retried)
    retried.reject.assert_awaited_once_with(requeue=False)
    error_exchange.publish.assert_not_awaited()

    exhausted = event_message("order.created", {"order_ids": 1})
    exhausted.headers = {"x-death": [{"count": consumer.max_retries}]}
    await consumer.process_event_log(exhausted)

    parked = error_exchange.publish.await_args
    assert parked.kwargs["routing_key"] == "event_log_queue.error"
    assert parked.args[0].headers["x-original-routing-key"] == "order.created"
    assert parked.args[0].message_id == "m-1"
    exhausted.ack.assert_awaited_once()


@pytest.mark.anyio
async def test_find_builds_query_from_filters():
    collection = Collection([{"_id": "a"}, {"_id": "b"}, {"_id": "c"}])
    repository = EventRepository(collection)

    documents = await repository.find(EventFilter(event="order.created", user_id=5, before=OCCURRED_AT, limit=2))

    assert collection.query == {"event": "order.created", "user_ids": 5, "occurred_at": {"$lt": OCCURRED_AT}}
    assert collection.sorted_by == ("occurred_at", DESCENDING)
    assert collection.limited_to == 2
    assert [doc["_id"] for doc in documents] == ["a", "b"]

    await repository.find(EventFilter())
    assert collection.query == {}


@pytest.mark.anyio
async def test_indexes_include_ttl_for_retention():
    collection = Collection()

    await EventRepository(collection).ensure_indexes(ttl_days=30)

    ttl = [kwargs for keys, kwargs in collection.indexes if "expireAfterSeconds" in kwargs]
    assert ttl == [{"name": "occurred_at_ttl", "expireAfterSeconds": 30 * 86400}]
    assert len(collection.indexes) == 5


@pytest.mark.anyio
async def test_service_maps_documents_and_reports_unavailable_mongo():
    document = build_event("order.deleted", {"order_ids": 7}, "m-9", OCCURRED_AT)
    service = EventLogService(EventRepository(Collection([document])))

    [event] = await service.list_events(EventFilter())
    assert event.id == "m-9" and event.order_ids == [7]

    broken = EventLogService(SimpleNamespace(find=AsyncMock(side_effect=ServerSelectionTimeoutError("down"))))
    with pytest.raises(EventLogUnavailableError):
        await broken.list_events(EventFilter())


class FakeChannel:
    def __init__(self):
        self.queues = {}
        self.default_exchange = SimpleNamespace(publish=AsyncMock())

    async def set_qos(self, prefetch_count):
        pass

    async def declare_exchange(self, name, exchange_type, durable):
        return name

    async def declare_queue(self, name, durable, arguments=None):
        queue = SimpleNamespace(name=name, arguments=arguments, bindings=[], consume=AsyncMock())

        async def bind(exchange, routing_key):
            queue.bindings.append((exchange, routing_key))

        queue.bind = bind
        self.queues[name] = queue
        return queue


async def connect_consumer(monkeypatch, events):
    channel = FakeChannel()

    async def connect_robust(url):
        return SimpleNamespace(channel=AsyncMock(return_value=channel))

    monkeypatch.setattr(queue_consumer.aio_pika, "connect_robust", connect_robust)
    consumer = queue_consumer.QueueConsumer(SimpleNamespace(), "amqp://test", events=events)
    await consumer.start()
    return channel


@pytest.mark.anyio
async def test_event_log_queue_is_bound_to_every_event_with_retry_and_error_queues(monkeypatch):
    channel = await connect_consumer(monkeypatch, events=EventRepository(Collection()))

    queue = channel.queues["event_log_queue"]
    assert sorted(queue.bindings) == sorted(queue_consumer.ALL_EVENTS)
    assert sorted(channel.queues["cache_queue"].bindings) == sorted(queue_consumer.ALL_EVENTS)
    assert channel.queues["notification_queue"].bindings == [("order_exchange", "order.paid")]
    assert queue.arguments["x-dead-letter-routing-key"] == "event_log_queue.retry"
    assert channel.queues["event_log_queue.retry"].arguments["x-dead-letter-routing-key"] == "event_log_queue"
    assert "event_log_queue.error" in channel.queues


@pytest.mark.anyio
async def test_event_log_queue_is_not_declared_without_repository(monkeypatch):
    channel = await connect_consumer(monkeypatch, events=None)

    assert "event_log_queue" not in channel.queues
    assert "cache_queue" in channel.queues


@pytest.mark.anyio
async def test_published_event_has_stable_id_and_timestamp_across_retries(monkeypatch):
    producer, _ = build_producer(monkeypatch, [ConnectionError("down"), None])

    await producer.publish_event("order_exchange", "order.created", {"order_ids": 1})

    first, second = [call.args[0] for call in producer.exchanges["order_exchange"].publish.await_args_list]
    assert first.message_id and first.message_id == second.message_id
    assert first.timestamp == second.timestamp is not None


@pytest.mark.anyio
async def test_mongo_down_only_degrades_readiness():
    async def ok():
        return True

    service = HealthService({}, SimpleNamespace(ping=ok), SimpleNamespace(ensure_connected=AsyncMock(return_value=True)),
                            mongo=SimpleNamespace(admin=SimpleNamespace(
                                command=AsyncMock(side_effect=ServerSelectionTimeoutError("down")))))

    result = await service.readiness()

    assert result["status"] == "degraded"
    assert result["checks"]["mongodb"] == "fail"


client = TestClient(app)


def use_events(service, user):
    async def current_user():
        return user

    app.dependency_overrides[dependencies.get_current_user] = current_user
    app.dependency_overrides[dependencies.get_event_log_service] = lambda: service


def teardown_function():
    app.dependency_overrides.clear()


def test_event_log_is_admin_only():
    service = SimpleNamespace(list_events=AsyncMock(return_value=[]))
    use_events(service, SimpleNamespace(id=1, is_admin=False, is_active=True))

    assert client.get("/v1/events/").status_code == 403
    service.list_events.assert_not_awaited()


def test_event_log_filters_are_passed_and_validated():
    service = SimpleNamespace(list_events=AsyncMock(return_value=[]))
    use_events(service, SimpleNamespace(id=9, is_admin=True, is_active=True))

    response = client.get("/v1/events/", params={"event": "order.created", "user_id": 5, "limit": 10})

    assert response.status_code == 200
    [filters] = service.list_events.await_args.args
    assert filters == EventFilter(event="order.created", user_id=5, limit=10)
    assert client.get("/v1/events/", params={"limit": 1000}).status_code == 422


def test_event_log_returns_503_when_mongo_is_down():
    service = EventLogService(SimpleNamespace(find=AsyncMock(side_effect=ServerSelectionTimeoutError("down"))))
    use_events(service, SimpleNamespace(id=9, is_admin=True, is_active=True))

    response = client.get("/v1/events/")

    assert response.status_code == 503
    assert response.json() == {"detail": "Журнал событий временно недоступен"}
