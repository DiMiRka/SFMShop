from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Review
from src.repositories.base_repository import BaseRepository


class ReviewRepository(BaseRepository):
    def __init__(self, db: AsyncSession):
        super().__init__(db)

    async def get_all(self, limit: int = 100, offset: int = 0) -> list[Review]:
        result = await self.db.execute(select(Review).order_by(Review.id).offset(offset).limit(limit))
        return list(result.scalars().all())

    async def get_by_product(self, product_id: int, limit: int = 20, offset: int = 0) -> list[Review]:
        result = await self.db.execute(
            select(Review)
            .where(Review.product_id == product_id)
            .order_by(Review.created_at.desc(), Review.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_by_id(self, review_id: int) -> Review | None:
        result = await self.db.execute(select(Review).where(Review.id == review_id))
        return result.scalar_one_or_none()

    async def get_by_id_for_update(self, review_id: int) -> Review | None:
        result = await self.db.execute(select(Review).where(Review.id == review_id).with_for_update())
        return result.scalar_one_or_none()

    async def get_by_product_and_user(self, product_id: int, user_id: int) -> Review | None:
        result = await self.db.execute(
            select(Review).where(Review.product_id == product_id, Review.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def create(self, data: dict) -> Review:
        review = Review(**data)
        self.db.add(review)
        await self.db.flush()
        return review

    async def update(self, review: Review, data: dict) -> None:
        for field, value in data.items():
            setattr(review, field, value)
        await self.db.flush()

    async def delete(self, review: Review) -> None:
        await self.db.delete(review)
