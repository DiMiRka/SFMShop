import json
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

from sfmshop.api.main import sfmshop_app as app
from sfmshop.core import dependencies
from sfmshop.core.exceptions import EmbeddingUnavailableError
from sfmshop.core.limiter import limiter
from sfmshop.repositories.product_repository import SearchResult
from sfmshop.schemas.assistant import SemanticSearchProductsArgs
from sfmshop.services.product_search_service import ProductSearchService, fuse
from tests.test_assistant_service import ScriptedLLM, call, final, make_service
from tests.test_embeddings import FakeEmbeddingClient
from tests.test_services import ProductRepoFake, db_product


pytestmark = pytest.mark.anyio

MOUSE = db_product(1, "Мышь беспроводная", Decimal("990.00"), 3)
PAD = db_product(2, "Коврик", Decimal("300.00"), 0)
HEADPHONES = db_product(3, "Наушники для бега", Decimal("4500.00"), 2)


def metric(mode):
    return REGISTRY.get_sample_value("sfmshop_semantic_searches_total", {"mode": mode}) or 0


class HybridRepo(ProductRepoFake):
    def __init__(self, text=(), semantic=()):
        super().__init__()
        self.text = list(text)
        self.semantic = list(semantic)
        self.calls = {}

    async def search(self, **filters):
        self.calls["text"] = filters
        return SearchResult(self.text, len(self.text), False)

    async def semantic_search(self, vector, max_distance, **filters):
        self.calls["semantic"] = {"vector": vector, "max_distance": max_distance, **filters}
        return self.semantic


class MemoryCache:
    def __init__(self):
        self.data = {}

    async def get_or_set_cache(self, key, func, ttl=900):
        if key not in self.data:
            self.data[key] = (await func(), ttl)
        return self.data[key][0]


def test_products_found_both_ways_rank_first():
    result = fuse(semantic=[(HEADPHONES, 0.2), (MOUSE, 0.4)], text=[PAD, MOUSE], limit=10)

    assert [p["id"] for p in result] == [1, 2, 3]
    assert result[0]["matched_by"] == ["semantic", "text"]
    assert result[0]["similarity"] == 0.6
    assert result[1]["similarity"] is None and result[1]["matched_by"] == ["text"]
    assert result[0]["price"] == "990.00"
    assert [p["id"] for p in fuse([(HEADPHONES, 0.2), (MOUSE, 0.4)], [PAD, MOUSE], limit=2)] == [1, 2]


async def test_hybrid_search_passes_filters_and_similarity_threshold_to_both_searches():
    repo = HybridRepo(text=[MOUSE], semantic=[(HEADPHONES, 0.25)])
    embeddings = FakeEmbeddingClient()
    service = ProductSearchService(repo, MemoryCache(), embeddings, min_similarity=0.3)
    hybrid = metric("hybrid")

    result = await service.hybrid_search("  подарок   бегуну ", limit=5, max_price=Decimal("5000"), in_stock=True)

    assert result["query"] == "подарок бегуну" and result["mode"] == "hybrid"
    assert {p["id"] for p in result["products"]} == {1, 3}
    filters = {"min_price": None, "max_price": Decimal("5000"), "in_stock": True, "limit": 5}
    assert repo.calls["text"] == {"name_query": "подарок бегуну", **filters}
    assert repo.calls["semantic"]["max_distance"] == pytest.approx(0.7)
    assert {key: repo.calls["semantic"][key] for key in filters} == filters
    assert embeddings.calls == [["подарок бегуну"]]
    assert metric("hybrid") == hybrid + 1


async def test_query_embedding_is_cached_per_model():
    embeddings = FakeEmbeddingClient()
    cache = MemoryCache()
    service = ProductSearchService(HybridRepo(), cache, embeddings, min_similarity=0.3, query_cache_ttl=60)

    await service.hybrid_search("подарок бегуну")
    await service.hybrid_search("подарок  бегуну")

    assert embeddings.calls == [["подарок бегуну"]]
    [(key, (_, ttl))] = cache.data.items()
    assert key.startswith("embedding:fake-embedding:") and ttl == 60


async def test_search_works_by_name_only_when_embeddings_are_disabled():
    repo = HybridRepo(text=[MOUSE])
    text = metric("text")

    result = await ProductSearchService(repo, MemoryCache(), None, min_similarity=0.3).hybrid_search("мышь")

    assert result["mode"] == "text" and [p["id"] for p in result["products"]] == [1]
    assert "semantic" not in repo.calls
    assert metric("text") == text + 1


async def test_search_falls_back_to_name_when_embeddings_api_is_down():
    class DownClient(FakeEmbeddingClient):
        async def embed(self, texts):
            raise EmbeddingUnavailableError("down")

    repo = HybridRepo(text=[MOUSE])
    fallback = metric("fallback")

    result = await ProductSearchService(repo, MemoryCache(), DownClient(), min_similarity=0.3).hybrid_search("мышь")

    assert result["mode"] == "text" and [p["id"] for p in result["products"]] == [1]
    assert metric("fallback") == fallback + 1


client = TestClient(app)


@pytest.fixture
def search_service():
    service = MagicMock()
    service.hybrid_search = AsyncMock(return_value={"query": "подарок бегуну", "mode": "hybrid", "products": [{
        "id": 3, "name": "Наушники для бега", "description": None, "price": "4500.00", "quantity": 2,
        "created_at": "2026-01-01T00:00:00", "similarity": 0.62, "matched_by": ["semantic"],
    }]})

    async def override():
        return service

    app.dependency_overrides[dependencies.get_product_search_service] = override
    limiter.reset()
    yield service
    app.dependency_overrides.clear()
    limiter.reset()


def test_semantic_search_endpoint_is_not_taken_for_product_id(search_service):
    response = client.get("/v1/products/semantic-search",
                          params={"q": "подарок бегуну", "limit": 5, "max_price": "5000", "in_stock": True})

    assert response.status_code == 200, response.text
    assert response.json()["products"][0] == {
        "id": 3, "name": "Наушники для бега", "description": None, "price": "4500.00", "quantity": 2,
        "created_at": "2026-01-01T00:00:00", "similarity": 0.62, "matched_by": ["semantic"],
    }
    search_service.hybrid_search.assert_awaited_once_with(
        "подарок бегуну", limit=5, min_price=None, max_price=Decimal("5000"), in_stock=True)


@pytest.mark.parametrize("params", [{"q": "a"}, {"q": "мышь", "limit": 21}, {"q": "мышь", "min_price": "-1"}])
def test_semantic_search_validates_query(search_service, params):
    assert client.get("/v1/products/semantic-search", params=params).status_code == 422


def test_semantic_search_is_rate_limited_because_each_query_costs_money(search_service):
    statuses = [client.get("/v1/products/semantic-search", params={"q": "мышь"}).status_code for _ in range(31)]

    assert statuses[:30] == [200] * 30 and statuses[30] == 429


async def test_assistant_answers_from_semantic_search_results_only():
    headphones = db_product(3, "Наушники для бега", Decimal("4500.00"), 2)
    headphones.description = "Беспроводные, защита от пота"
    repo = HybridRepo(semantic=[(headphones, 0.3)])
    llm = ScriptedLLM([
        call("semantic_search_products", {"query": "что подарить бегуну", "max_price": "5000"}),
        final("Подойдут наушники для бега за 4500 ₽", product_ids=[3, 99]),
    ])

    response = await make_service(llm, product_rep=repo, embeddings=FakeEmbeddingClient()).ask("что подарить бегуну?")

    [result] = llm.calls[1]["messages"][-1].results
    assert json.loads(result.content) == [{
        "id": 3, "name": "Наушники для бега", "description": "Беспроводные, защита от пота", "price": "4500.00",
        "quantity": 2, "similarity": 0.7, "matched_by": ["semantic"],
    }]
    assert response.product_ids == [3]
    assert repo.calls["semantic"]["max_price"] == Decimal("5000")


def test_semantic_tool_rejects_inverted_price_range():
    with pytest.raises(ValueError):
        SemanticSearchProductsArgs(query="подарок", min_price=Decimal("10"), max_price=Decimal("5"))
