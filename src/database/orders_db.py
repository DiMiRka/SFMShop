from fastapi import HTTPException
from sqlalchemy import select, update, text
from loguru import logger
import asyncio

from src.models.exceptions import InsufficientStockError, BusinessLogicError
from src.database.connection import write_db_dependency, redis_client
from src.database.models import Order, User, Product, OrderItem
from src.services.cache_service import CacheService
from src.schemas import OrderCreate

cache = CacheService(redis_client)


async def create_order_db(db: write_db_dependency, order: OrderCreate):
    quantity = []
    product_ids = []

    for item in order.items:
        item_quantity = item.quantity
        if item_quantity <= 0:
            raise ValueError("Количество должно быть положительным")

        quantity.append(item_quantity)
        product_ids.append(item.product_id)

    user_id = order.user_id

    async with db.begin():
        await db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))

        result = await db.execute(select(User).where(User.id == user_id).with_for_update())
        user_db = result.scalar_one_or_none()

        if not user_db:
            logger.warning(f"User id={user_id} not found")
            raise HTTPException(status_code=404, detail="Пользователь не найден")

        result = await db.execute(
            select(Product)
            .where(Product.id.in_(product_ids))
            .with_for_update()
        )

        products_db = {p.id: p for p in result.scalars().all()}

        order_items_db = []
        total = 0

        for idx, product_id in enumerate(product_ids):
            product_db = products_db.get(product_id)

            if not product_db:
                logger.warning(f"Product id={product_id} not found")
                raise HTTPException(status_code=404, detail="Товар не найден")

            if product_db.quantity < quantity[idx]:
                raise InsufficientStockError("Недостаточно товара на складе")

            product_total = 0

            product_db.quantity -= quantity[idx]

            product_total += product_db.price * quantity[idx]

            total += product_total

            order_items_db.append((product_db.id, quantity[idx], product_total))

        if user_db.balance < total:
            raise BusinessLogicError("Недостаточно средств на балансе пользователя")

        user_db.balance -= total

        order = Order(user=user_db, items=[])
        db.add(order)
        await db.flush()

        for item in order_items_db:
            order_item = OrderItem(
                order_id=order.id,
                product_id=item[0],
                quantity=item[1],
                total=item[2],
            )
            db.add(order_item)

    task_1 = cache.delete_products(product_ids)
    task_2 = cache.delete_users(order.user_id)
    task_3 = cache.delete_orders(order.user_id)

    await asyncio.gather(task_1, task_2, task_3)

    return {
        "order_id": order.id,
        "user_id": user_db.id,
        "products_id": product_ids,
        "quantity": quantity,
        "total": float(total),
    }


async def delete_order_db(db: write_db_dependency, order_id):

    async with db.begin():

        result = await db.execute(select(Order).where(Order.id == order_id))
        order = result.scalar_one_or_none()

        if not order:
            logger.warning(f"Order id={order_id} not found")
            raise HTTPException(status_code=404, detail="Заказ не найден")

        await db.delete(order)
        await db.execute(update(User).where(User.id == order.user_id).values(balance=User.balance + order.total))

        result = await db.execute(select(OrderItem).where(OrderItem.order_id == order.id))
        items = result.scalars().all()

        for item in items:
            await db.execute(
                update(Product)
                .where(Product.id == item.product_id)
                .values(quantity=Product.quantity + item.quantity)
            )

        product_ids = [item.product_id for item in items]

    task_1 = cache.delete_products(product_ids)
    task_2 = cache.delete_users(order.user_id)
    task_3 = cache.delete_orders(order.user_id)

    await asyncio.gather(task_1, task_2, task_3)

    return {"id": order_id, "message": "Заказ удален"}
