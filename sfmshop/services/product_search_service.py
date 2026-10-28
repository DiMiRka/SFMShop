import hashlib
from collections import defaultdict
from decimal import Decimal

from sfmshop.clients.embeddings import EmbeddingClient
from sfmshop.core.exceptions import EmbeddingUnavailableError
from sfmshop.core.metrics import SEMANTIC_SEARCHES
from sfmshop.database.models import Product
from sfmshop.repositories.product_repository import ProductRepository
from sfmshop.schemas.products import ProductResponse
from sfmshop.services.cache_service import CacheService


RRF_K = 60


class ProductSearchService:
    def __init__(
            self,
            product_rep: ProductRepository,
            cache: CacheService,
            embeddings: EmbeddingClient | None,
            min_similarity: float,
            query_cache_ttl: int = 86400):
        self.product_rep = product_rep
        self.cache = cache
        self.embeddings = embeddings
        self.min_similarity = min_similarity
        self.query_cache_ttl = query_cache_ttl

    async def hybrid_search(
            self,
            query: str,
            limit: int = 10,
            min_price: Decimal | None = None,
            max_price: Decimal | None = None,
            in_stock: bool = False) -> dict:
        query = " ".join(query.split())
        text_result = await self.product_rep.search(
            name_query=query, min_price=min_price, max_price=max_price, in_stock=in_stock, limit=limit)
        semantic: list[tuple[Product, float]] = []
        mode = "text"

        if self.embeddings is not None:
            try:
                vector = await self._embed_query(self.embeddings, query)
            except EmbeddingUnavailableError:
                SEMANTIC_SEARCHES.labels("fallback").inc()
            else:
                semantic = await self.product_rep.semantic_search(
                    vector, 1 - self.min_similarity, min_price=min_price, max_price=max_price, in_stock=in_stock,
                    limit=limit)
                mode = "hybrid"
                SEMANTIC_SEARCHES.labels("hybrid").inc()
        else:
            SEMANTIC_SEARCHES.labels("text").inc()

        return {"query": query, "mode": mode, "products": fuse(semantic, text_result.products, limit)}

    async def _embed_query(self, embeddings: EmbeddingClient, query: str) -> list[float]:
        async def fetch():
            [vector] = await embeddings.embed([query])
            return vector

        key = f"embedding:{embeddings.model}:{hashlib.sha256(query.encode()).hexdigest()}"
        return await self.cache.get_or_set_cache(key, fetch, ttl=self.query_cache_ttl)


def fuse(semantic: list[tuple[Product, float]], text: list[Product], limit: int) -> list[dict]:
    scores: dict[int, float] = defaultdict(float)
    products: dict[int, Product] = {}
    similarity: dict[int, float] = {}
    matched_by: dict[int, list[str]] = defaultdict(list)

    for rank, (product, distance) in enumerate(semantic, start=1):
        scores[product.id] += 1 / (RRF_K + rank)
        products[product.id] = product
        similarity[product.id] = round(1 - distance, 4)
        matched_by[product.id].append("semantic")

    for rank, product in enumerate(text, start=1):
        scores[product.id] += 1 / (RRF_K + rank)
        products[product.id] = product
        matched_by[product.id].append("text")

    ranked = sorted(scores, key=lambda product_id: (-scores[product_id], product_id))[:limit]
    return [
        {
            **ProductResponse.model_validate(products[product_id]).model_dump(mode="json"),
            "similarity": similarity.get(product_id),
            "matched_by": matched_by[product_id],
        }
        for product_id in ranked
    ]
