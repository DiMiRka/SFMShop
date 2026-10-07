from decimal import Decimal
from typing import cast
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from src.repositories.base_repository import BaseRepository
from src.database.models import Product

SEARCH_LIMIT_MAX = 20


class ProductRepository(BaseRepository):
    def __init__(self, db: AsyncSession):
        super().__init__(db)

    async def get_all(self, limit: int = 100, offset: int = 0) -> list[Product]:
        result = await self.db.execute(select(Product).offset(offset).limit(limit))
        return list(result.scalars().all())

    async def get_by_ids(self, ids: list[int]) -> list[Product]:
        result = await self.db.execute(select(Product).where(Product.id.in_(ids)))
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
            limit: int = 10) -> list[Product]:
        query = select(Product)

        if name_query:
            escaped = name_query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            query = query.where(Product.name.ilike(f"%{escaped}%", escape="\\"))
        if min_price is not None:
            query = query.where(Product.price >= min_price)
        if max_price is not None:
            query = query.where(Product.price <= max_price)
        if in_stock:
            query = query.where(Product.quantity > 0)

        limit = max(1, min(limit, SEARCH_LIMIT_MAX))
        result = await self.db.execute(query.order_by(Product.price, Product.id).limit(limit))
        return list(result.scalars().all())

    async def get_by_ids_for_update(self, ids: list[int]) -> list[Product]:
        result = await self.db.execute(
            select(Product)
            .where(Product.id.in_(ids))
            .with_for_update()
        )
        return list(result.scalars().all())

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

    async def get_count_all(self) -> int:
        result = await self.db.execute(select(func.count()).select_from(Product))
        return cast(int, result.scalar())
