from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select

from src.repositories.base_repository import BaseRepository
from src.database.models import Order, OrderItem


class OrderRepository(BaseRepository):
    def __init__(self, db: AsyncSession):
        super().__init__(db)

    async def get_all(self, limit: int = 100, offset: int = 0) -> list[Order] | None:
        result = await self.db.execute(select(Order).options(selectinload(Order.items)).offset(offset).limit(limit))
        return list(result.scalars().all())

    async def get_by_id(self, order_id: int) -> Order | None:
        result = await self.db.execute(select(Order).options(selectinload(Order.items)).where(Order.id == order_id))
        return result.scalar_one_or_none()

    async def get_by_id_for_update(self, order_id: int) -> Order | None:
        result = await self.db.execute(
            select(Order).
            options(selectinload(Order.items)).
            where(Order.id == order_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_order_products(self, order_id: int) -> list[OrderItem]:
        result = await self.db.execute(select(OrderItem).where(OrderItem.order_id == order_id))
        return list(result.scalars().all())

    async def get_user_orders(self, user_id: int) -> list[Order]:
        result = await self.db.execute(select(Order).options(selectinload(Order.items)).where(Order.user_id == user_id))
        return list(result.scalars().all())

    async def get_order_ids_by_user(self, user_id: int) -> list[int] | None:
        result = await self.db.execute(select(Order.id).where(Order.user_id == user_id))
        orders = list(result.scalars().all())

        return orders if orders else None

    async def get_product_ids_by_user(self, user_id: int) -> list[int] | None:
        result = await self.db.execute(select(OrderItem.product_id)
                                       .join(Order, OrderItem.order_id == Order.id)
                                       .where(Order.user_id == user_id))
        products = list(result.scalars().all())

        return products if products else None

    async def create(self, data: dict) -> int:
        order_db = Order(**data)
        self.db.add(order_db)

        await self.db.flush()

        return order_db.id

    async def create_order_item(self, data: dict) -> OrderItem:
        order_item_db = OrderItem(**data)
        self.db.add(order_item_db)

        await self.db.flush()
        return order_item_db

    async def delete(self, order: Order) -> None:
        await self.db.delete(order)
