from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from src.repositories.base_repository import BaseRepository
from src.database.models import Product


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
        return result.scalar()



