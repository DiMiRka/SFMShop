import asyncio
import os
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import create_async_engine

from sfmshop.core.config import app_settings
from sfmshop.database.connection import create_sessionmaker
from sfmshop.database.models import EMBEDDING_DIMENSIONS, Product, ProductEmbedding
from sfmshop.services.product_index_service import ProductIndexer
from tests.test_embeddings import FakeEmbeddingClient, fake_vector


pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_INTEGRATION_TESTS"),
    reason="нужен PostgreSQL с pgvector после миграций (в CI задаётся RUN_INTEGRATION_TESTS=1)",
)


def test_indexer_stores_vectors_in_pgvector_and_cascade_removes_them():
    async def scenario():
        engine = create_async_engine(app_settings.postgres_url)
        session_factory = create_sessionmaker(engine)
        client = FakeEmbeddingClient(dimensions=EMBEDDING_DIMENSIONS)
        indexer = ProductIndexer(session_factory, client)
        name = f"Наушники {uuid.uuid4().hex[:8]}"
        try:
            async with session_factory() as session:
                product = Product(name=name, description="Беспроводные", price=Decimal("990.00"), quantity=1)
                session.add(product)
                await session.commit()
                product_id = product.id

            first = await indexer.index([product_id])
            second = await indexer.index([product_id])

            vector = fake_vector(f"{name}\nБеспроводные", EMBEDDING_DIMENSIONS)
            async with session_factory() as session:
                stored = await session.get(ProductEmbedding, product_id)
                nearest = await session.scalar(
                    select(ProductEmbedding.product_id)
                    .order_by(ProductEmbedding.embedding.cosine_distance(vector))
                    .limit(1)
                )
                await session.execute(delete(Product).where(Product.id == product_id))
                await session.commit()
                left = await session.get(ProductEmbedding, product_id, populate_existing=True)

            return first, second, stored, nearest, left, vector, product_id
        finally:
            await engine.dispose()

    first, second, stored, nearest, left, vector, product_id = asyncio.run(scenario())

    assert (first.indexed, second.unchanged) == (1, 1)
    assert stored.model == "fake-embedding"
    assert stored.embedding == pytest.approx(vector, abs=1e-6)
    assert nearest == product_id
    assert left is None
