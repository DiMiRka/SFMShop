import hashlib
from collections.abc import Callable
from dataclasses import dataclass

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from sfmshop.clients.embeddings import EmbeddingClient
from sfmshop.core.metrics import PRODUCTS_INDEXED
from sfmshop.database.models import Product
from sfmshop.repositories.product_embedding_repository import ProductEmbeddingRepository
from sfmshop.repositories.product_repository import ProductRepository


def product_text(product: Product) -> str:
    return "\n".join(part for part in (product.name, product.description) if part)


def content_hash(model: str, text: str) -> str:
    return hashlib.sha256(f"{model}\n{text}".encode()).hexdigest()


@dataclass(frozen=True)
class IndexResult:
    indexed: int = 0
    unchanged: int = 0
    missing: int = 0


class ProductIndexer:
    def __init__(
            self,
            session_factory: Callable[[], AsyncSession],
            client: EmbeddingClient,
            products_repository: Callable[[AsyncSession], ProductRepository] = ProductRepository,
            embeddings_repository: Callable[[AsyncSession], ProductEmbeddingRepository] = ProductEmbeddingRepository):
        self.session_factory = session_factory
        self.client = client
        self.products_repository = products_repository
        self.embeddings_repository = embeddings_repository

    async def index(self, product_ids: list[int], force: bool = False) -> IndexResult:
        ids = sorted(set(product_ids))
        async with self.session_factory() as session:
            products = await self.products_repository(session).get_by_ids(ids)
            known = {} if force else await self.embeddings_repository(session).get_hashes(ids)

        pending = []
        for product in products:
            text = product_text(product)
            digest = content_hash(self.client.model, text)
            if known.get(product.id) != digest:
                pending.append((product.id, text, digest))

        rows = []
        if pending:
            vectors = await self.client.embed([text for _, text, _ in pending])
            async with self.session_factory() as session:
                existing = await self.products_repository(session).lock_existing_ids([pid for pid, _, _ in pending])
                rows = [
                    {"product_id": product_id, "embedding": vector, "model": self.client.model,
                     "content_hash": digest}
                    for (product_id, _, digest), vector in zip(pending, vectors, strict=True)
                    if product_id in existing
                ]
                if rows:
                    await self.embeddings_repository(session).upsert(rows)
                await session.commit()

        unchanged = len(products) - len(pending)
        result = IndexResult(indexed=len(rows), unchanged=unchanged, missing=len(ids) - len(rows) - unchanged)
        PRODUCTS_INDEXED.labels("indexed").inc(result.indexed)
        PRODUCTS_INDEXED.labels("unchanged").inc(result.unchanged)
        PRODUCTS_INDEXED.labels("missing").inc(result.missing)
        logger.info(f"products_indexed indexed={result.indexed} unchanged={result.unchanged} "
                    f"missing={result.missing}")
        return result
