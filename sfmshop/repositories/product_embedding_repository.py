from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from sfmshop.database.models import ProductEmbedding


class ProductEmbeddingRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_hashes(self, product_ids: list[int]) -> dict[int, str]:
        result = await self.db.execute(
            select(ProductEmbedding.product_id, ProductEmbedding.content_hash)
            .where(ProductEmbedding.product_id.in_(product_ids))
        )
        return {product_id: content_hash for product_id, content_hash in result.tuples()}

    async def upsert(self, rows: list[dict]) -> None:
        statement = insert(ProductEmbedding).values(rows)
        await self.db.execute(statement.on_conflict_do_update(
            index_elements=[ProductEmbedding.product_id],
            set_={
                "embedding": statement.excluded.embedding,
                "model": statement.excluded.model,
                "content_hash": statement.excluded.content_hash,
                "updated_at": func.now(),
            },
        ))
