import array
import base64
import hashlib
import json
from types import SimpleNamespace

import httpx2
import openai
import pytest
from prometheus_client import REGISTRY

from sfmshop.clients.embeddings import OpenAIEmbeddingClient, create_embedding_client
from sfmshop.core.config import AppSettings
from sfmshop.core.exceptions import EmbeddingUnavailableError
from sfmshop.database.models import Product
from sfmshop.schemas import ProductUpdate
from sfmshop.services.product_index_service import ProductIndexer, content_hash, product_text
from sfmshop.services.product_service import ProductService
from sfmshop.services.queue_consumer import QueueConsumer
from tests.test_queue import FakeMessage
from tests.test_services import ACTOR, FakeCache, FakeQueue, ProductRepoFake


pytestmark = pytest.mark.anyio


def metric(name, **labels):
    return REGISTRY.get_sample_value(name, labels) or 0


def fake_vector(text, dimensions=8):
    digest = hashlib.sha256(text.encode()).digest()
    return [round(byte / 255, 4) for byte in digest[:dimensions]]


class FakeEmbeddingClient:
    model = "fake-embedding"

    def __init__(self, dimensions=8):
        self.dimensions = dimensions
        self.calls = []

    async def embed(self, texts):
        self.calls.append(list(texts))
        return [fake_vector(text, self.dimensions) for text in texts]

    async def close(self):
        pass


def embedding_body(vectors, tokens=10, shuffle=False):
    data = [{"object": "embedding", "index": i, "embedding": vector} for i, vector in enumerate(vectors)]
    return {
        "object": "list",
        "model": "text-embedding-3-small",
        "data": list(reversed(data)) if shuffle else data,
        "usage": {"prompt_tokens": tokens, "total_tokens": tokens},
    }


ERROR_BODY = {"error": {"message": "slow down", "type": "rate_limit_error", "code": None, "param": None}}


class Transport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, request):
        self.requests.append(json.loads(request.content))
        status, body = self.responses.pop(0)
        return httpx2.Response(status, json=body, headers={"retry-after-ms": "1"})


def make_client(transport, batch_size=100, max_retries=2):
    return OpenAIEmbeddingClient(
        api_key="test-key",
        model="text-embedding-3-small",
        dimensions=3,
        batch_size=batch_size,
        usd_per_million_tokens=0.02,
        timeout=5,
        max_retries=max_retries,
        http_client=openai.DefaultAsyncHttpxClient(transport=httpx2.MockTransport(transport)),
    )


async def test_texts_are_sent_in_batches_and_vectors_keep_input_order():
    transport = Transport([
        (200, embedding_body([[1, 0, 0], [0, 1, 0]], shuffle=True)),
        (200, embedding_body([[0, 0, 1]])),
    ])
    client = make_client(transport, batch_size=2)

    vectors = await client.embed(["мышь", "клавиатура", "монитор"])

    assert vectors == [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
    assert [request["input"] for request in transport.requests] == [["мышь", "клавиатура"], ["монитор"]]
    assert all(request["model"] == "text-embedding-3-small" and request["dimensions"] == 3
               for request in transport.requests)


async def test_base64_vectors_from_api_are_decoded():
    packed = base64.b64encode(array.array("f", [0.5, -0.25, 1.0]).tobytes()).decode()
    transport = Transport([(200, embedding_body([packed]))])

    assert await make_client(transport).embed(["мышь"]) == [[0.5, -0.25, 1.0]]
    assert transport.requests[0]["encoding_format"] == "base64"


async def test_tokens_and_cost_are_counted_per_model():
    tokens = metric("sfmshop_embedding_tokens_total", model="text-embedding-3-small")
    cost = metric("sfmshop_embedding_cost_usd_total", model="text-embedding-3-small")
    ok = metric("sfmshop_embedding_requests_total", result="ok")

    await make_client(Transport([(200, embedding_body([[1, 0, 0]], tokens=500_000))])).embed(["мышь"])

    assert metric("sfmshop_embedding_tokens_total", model="text-embedding-3-small") == tokens + 500_000
    assert metric("sfmshop_embedding_cost_usd_total", model="text-embedding-3-small") == pytest.approx(cost + 0.01)
    assert metric("sfmshop_embedding_requests_total", result="ok") == ok + 1


async def test_rate_limit_is_retried_then_succeeds():
    transport = Transport([(429, ERROR_BODY), (200, embedding_body([[1, 0, 0]]))])

    assert await make_client(transport).embed(["мышь"]) == [[1, 0, 0]]
    assert len(transport.requests) == 2


async def test_exhausted_retries_raise_unavailable():
    unavailable = metric("sfmshop_embedding_requests_total", result="unavailable")
    transport = Transport([(500, ERROR_BODY)] * 3)

    with pytest.raises(EmbeddingUnavailableError):
        await make_client(transport, max_retries=2).embed(["мышь"])

    assert len(transport.requests) == 3
    assert metric("sfmshop_embedding_requests_total", result="unavailable") == unavailable + 1


def test_embeddings_are_disabled_without_openai_key():
    assert create_embedding_client(AppSettings(_env_file=None, openai_api_key=None)) is None


def test_client_is_built_from_settings():
    client = create_embedding_client(AppSettings(_env_file=None, openai_api_key="key",
                                                 embedding_model="text-embedding-3-large", embedding_batch_size=5000))

    assert isinstance(client, OpenAIEmbeddingClient)
    assert client.model == "text-embedding-3-large"
    assert client.batch_size == 2048


@pytest.mark.parametrize("settings", [
    {"embedding_provider": "unknown"},
    {"embedding_dimensions": 512},
])
def test_wrong_embedding_settings_fail_on_startup(settings):
    with pytest.raises(ValueError):
        create_embedding_client(AppSettings(_env_file=None, openai_api_key="key", **settings))


def make_product(product_id, name, description=None):
    product = Product(name=name, description=description)
    product.id = product_id
    return product


class Session:
    def __init__(self):
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def commit(self):
        self.commits += 1


class Store:
    def __init__(self, products, hashes=None):
        self.products = {product.id: product for product in products}
        self.hashes = dict(hashes or {})
        self.upserted = []
        self.deleted_before_write = set()

    def products_repository(self, session):
        store = self

        class Products:
            async def get_by_ids(self, ids):
                return [store.products[i] for i in ids if i in store.products]

            async def lock_existing_ids(self, ids):
                return {i for i in ids if i in store.products and i not in store.deleted_before_write}

        return Products()

    def embeddings_repository(self, session):
        store = self

        class Embeddings:
            async def get_hashes(self, ids):
                return {i: h for i, h in store.hashes.items() if i in ids}

            async def upsert(self, rows):
                store.upserted += rows
                store.hashes.update({row["product_id"]: row["content_hash"] for row in rows})

        return Embeddings()


def make_indexer(store, client):
    return ProductIndexer(Session, client, store.products_repository, store.embeddings_repository)


def test_product_text_joins_name_and_description():
    assert product_text(make_product(1, "Мышь", "Беспроводная, 2.4 ГГц")) == "Мышь\nБеспроводная, 2.4 ГГц"
    assert product_text(make_product(1, "Мышь")) == "Мышь"


async def test_indexer_embeds_new_products_and_skips_unchanged():
    client = FakeEmbeddingClient()
    store = Store([make_product(1, "Мышь", "Беспроводная"), make_product(2, "Коврик")])
    indexer = make_indexer(store, client)

    first = await indexer.index([2, 1, 1])

    assert (first.indexed, first.unchanged, first.missing) == (2, 0, 0)
    assert client.calls == [["Мышь\nБеспроводная", "Коврик"]]
    assert store.upserted[0] == {
        "product_id": 1,
        "embedding": fake_vector("Мышь\nБеспроводная"),
        "model": "fake-embedding",
        "content_hash": content_hash("fake-embedding", "Мышь\nБеспроводная"),
    }

    store.products[2].description = "Резиновое основание"
    second = await indexer.index([1, 2])

    assert (second.indexed, second.unchanged, second.missing) == (1, 1, 0)
    assert client.calls[1] == ["Коврик\nРезиновое основание"]


async def test_force_recomputes_unchanged_products():
    client = FakeEmbeddingClient()
    store = Store([make_product(1, "Мышь")], hashes={1: content_hash("fake-embedding", "Мышь")})

    assert (await make_indexer(store, client).index([1])).unchanged == 1
    assert (await make_indexer(store, client).index([1], force=True)).indexed == 1
    assert client.calls == [["Мышь"]]


async def test_model_change_invalidates_old_vectors():
    store = Store([make_product(1, "Мышь")], hashes={1: content_hash("old-model", "Мышь")})

    assert (await make_indexer(store, FakeEmbeddingClient()).index([1])).indexed == 1


async def test_deleted_products_are_not_written():
    client = FakeEmbeddingClient()
    store = Store([make_product(1, "Мышь"), make_product(2, "Коврик")])
    store.deleted_before_write = {2}

    result = await make_indexer(store, client).index([1, 2, 3])

    assert (result.indexed, result.unchanged, result.missing) == (1, 0, 2)
    assert [row["product_id"] for row in store.upserted] == [1]


async def test_embedding_errors_leave_index_untouched():
    class BrokenClient(FakeEmbeddingClient):
        async def embed(self, texts):
            raise EmbeddingUnavailableError("down")

    store = Store([make_product(1, "Мышь")])

    with pytest.raises(EmbeddingUnavailableError):
        await make_indexer(store, BrokenClient()).index([1])

    assert store.upserted == []


async def test_product_update_event_reindexes_that_product():
    queue = FakeQueue()
    await ProductService(ProductRepoFake(), FakeCache(), queue).update_product(
        1, ProductUpdate(description="Беспроводная"), actor=ACTOR)
    _, routing_key, payload = queue.events[-1]
    consumer = QueueConsumer(FakeCache(), "amqp://test", indexer=SimpleNamespace(index=_recorder()))

    message = FakeMessage(routing_key, payload)
    await consumer.process_embedding(message)

    assert routing_key == "product.updated"
    assert consumer.indexer.index.calls == [[1]]
    message.ack.assert_awaited_once()


async def test_failed_indexing_is_retried_through_retry_queue():
    async def unavailable(ids):
        raise EmbeddingUnavailableError("down")

    consumer = QueueConsumer(FakeCache(), "amqp://test", indexer=SimpleNamespace(index=unavailable))
    message = FakeMessage("product.created", {"product_ids": 5}, retries=1)

    await consumer.process_embedding(message)

    message.reject.assert_awaited_once_with(requeue=False)


def _recorder():
    async def index(ids):
        index.calls.append(ids)
    index.calls = []
    return index
