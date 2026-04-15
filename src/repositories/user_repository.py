from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from decimal import Decimal

from src.repositories.base_repository import BaseRepository
from src.database.models import User


class UserRepository(BaseRepository):
    def __init__(self, db: AsyncSession):
        super().__init__(db)

    async def get_all(self, limit: int = 100, offset: int = 0) -> list[User]:
        result = await self.db.execute(select(User).offset(offset).limit(limit))
        return list(result.scalars().all())

    async def get_by_id(self, user_id: int) -> User | None:
        result = await self.db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_by_id_for_update(self, user_id: int) -> User | None:
        result = await self.db.execute(
            select(User).where(User.id == user_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        result = await self.db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def create(self, data: dict) -> User:
        user_db = User(**data)
        self.db.add(user_db)
        await self.db.flush()

        return user_db

    async def update(self, user_db: User, data: dict) -> None:
        for field, value in data.items():
            setattr(user_db, field, value)

        await self.db.flush()

    async def delete(self, user: User) -> None:
        await self.db.delete(user)

    async def get_balance(self, user_id: int) -> Decimal | None:
        result = await self.db.execute(select(User.balance).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_email(self, user_id: int) -> str | None:
        result = await self.db.execute(select(User.email).where(User.id == user_id))
        return result.scalar_one_or_none()
