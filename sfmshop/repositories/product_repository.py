from dataclasses import dataclass
from decimal import Decimal
from typing import cast
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import Select, select, func, text, update

from sfmshop.repositories.base_repository import BaseRepository
from sfmshop.database.models import Product, ProductEmbedding, Review

SEARCH_LIMIT_MAX = 100
FUZZY_MIN_LENGTH = 3


@dataclass(frozen=True)
class SearchResult:
    products: list[Product]
    total: int
    fuzzy: bool


class ProductRepository(BaseRepository):
    def __init__(self, db: AsyncSession):
        super().__init__(db)

    async def get_all(self, limit: int = 100, offset: int = 0) -> list[Product]:
        result = await self.db.execute(select(Product).offset(offset).limit(limit))
        return list(result.scalars().all())

    async def get_by_id(self, product_id: int) -> Product | None:
        result = await self.db.execute(select(Product).where(Product.id == product_id))
        return result.scalar_one_or_none()

    async def search(
            self,
            name_query: str | None = None,
            min_price: Decimal | None = None,
            max_price: Decimal | None = None,
            in_stock: bool = False,
            limit: int = 10,
            offset: int = 0) -> SearchResult:
        query = self._filtered(select(Product), min_price, max_price, in_stock)

        limit = max(1, min(limit, SEARCH_LIMIT_MAX))
        if not name_query:
            return await self._page(query, (Product.price, Product.id), limit, offset, fuzzy=False)

        escaped = name_query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        exact = query.where(Product.name.ilike(f"%{escaped}%", escape="\\"))
        result = await self._page(exact, (Product.price, Product.id), limit, offset, fuzzy=False)
        if result.total or len(name_query) < FUZZY_MIN_LENGTH:
            return result

        similar = query.where(Product.name.op("%>")(name_query))
        order = (func.word_similarity(name_query, Product.name).desc(), Product.price, Product.id)
        return await self._page(similar, order, limit, offset, fuzzy=True)

    async def semantic_search(
            self,
            vector: list[float],
            max_distance: float,
            min_price: Decimal | None = None,
            max_price: Decimal | None = None,
            in_stock: bool = False,
            limit: int = 10) -> list[tuple[Product, float]]:
        distance = ProductEmbedding.embedding.cosine_distance(vector)
        query = self._filtered(
            select(Product, distance.label("distance")).join(ProductEmbedding, ProductEmbedding.product_id == Product.id),
            min_price, max_price, in_stock,
        )

        await self.db.execute(text("SET LOCAL hnsw.iterative_scan = strict_order"))
        result = await self.db.execute(
            query.where(distance <= max_distance).order_by(distance).limit(max(1, min(limit, SEARCH_LIMIT_MAX)))
        )
        return [(product, float(product_distance)) for product, product_distance in result.tuples()]

    @staticmethod
    def _filtered(query: Select, min_price: Decimal | None, max_price: Decimal | None, in_stock: bool) -> Select:
        if min_price is not None:
            query = query.where(Product.price >= min_price)
        if max_price is not None:
            query = query.where(Product.price <= max_price)
        if in_stock:
            query = query.where(Product.quantity > 0)
        return query

    async def _page(self, query: Select, order: tuple, limit: int, offset: int, fuzzy: bool) -> SearchResult:
        total = await self.db.scalar(select(func.count()).select_from(query.subquery()))
        result = await self.db.execute(query.order_by(*order).offset(offset).limit(limit))
        return SearchResult(list(result.scalars().all()), total or 0, fuzzy)

    async def get_by_ids(self, ids: list[int]) -> list[Product]:
        result = await self.db.execute(select(Product).where(Product.id.in_(ids)).order_by(Product.id))
        return list(result.scalars().all())

    async def get_ids_after(self, after_id: int, limit: int) -> list[int]:
        result = await self.db.execute(
            select(Product.id).where(Product.id > after_id).order_by(Product.id).limit(limit)
        )
        return list(result.scalars().all())

    async def lock_existing_ids(self, ids: list[int]) -> set[int]:
        result = await self.db.execute(
            select(Product.id).where(Product.id.in_(ids)).with_for_update(key_share=True)
        )
        return set(result.scalars().all())

    async def get_by_ids_for_update(self, ids: list[int]) -> list[Product]:
        result = await self.db.execute(
            select(Product)
            .where(Product.id.in_(ids))
            .with_for_update()
        )
        return list(result.scalars().all())

    async def subtract_quantities(self, quantities: dict[int, int]) -> None:
        for product_id in sorted(quantities):
            await self.db.execute(
                update(Product)
                .where(Product.id == product_id)
                .values(quantity=func.greatest(Product.quantity - quantities[product_id], 0))
            )

    async def create(self, data: dict) -> int:
        product_db = Product(**data)
        self.db.add(product_db)
        await self.db.flush()

        return product_db.id

    async def update(self, product_db: Product, data: dict) -> None:
        for field, value in data.items():
            setattr(product_db, field, value)

        await self.db.flush()

    async def delete(self, product: Product) -> None:
        await self.db.delete(product)

    async def get_rating(self, product_id: int) -> tuple[float | None, int]:
        result = await self.db.execute(
            select(func.avg(Review.rating), func.count(Review.id)).where(Review.product_id == product_id)
        )
        average, count = result.one()
        return (round(float(average), 2) if average is not None else None), count

    async def get_count_all(self) -> int:
        result = await self.db.execute(select(func.count()).select_from(Product))
        return cast(int, result.scalar())
