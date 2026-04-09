from fastapi import HTTPException
from sqlalchemy import select, update, text

from src.models.exceptions import InsufficientStockError, BusinessLogicError
from src.database.connection import write_db_dependency, redis_client
from src.database.models import Order, User, Product, OrderItem
from src.services.cache_service import CacheService
from src.schemas import OrderCreate

cache = CacheService(redis_client)


async def create_order_db(db: write_db_dependency, order: OrderCreate):
    quantity = order.items[0].quantity
    product_id = order.items[0].product_id
    user_id = order.user_id

    if quantity <= 0:
        raise ValueError("Количество должно быть положительным")

    async with db.begin():
        await db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))

        result = await db.execute(select(Product).where(Product.id == product_id).with_for_update())
        product_db = result.scalar_one_or_none()

        if not product_db:
            raise HTTPException(status_code=404, detail="Товар не найден")

        if product_db.quantity < quantity:
            raise InsufficientStockError("Недостаточно товара на складе")

        product_db.quantity -= quantity

        result = await db.execute(select(User).where(User.id == user_id).with_for_update())
        user_db = result.scalar_one_or_none()

        if not user_db:
            raise HTTPException(status_code=404, detail="Пользователь не найден")

        total = product_db.price * quantity

        if user_db.balance < total:
            raise BusinessLogicError("Недостаточно средств на балансе пользователя")

        user_db.balance -= total

        order = Order(user=user_db, items=[])
        db.add(order)
        await db.flush()

        order_item = OrderItem(
            order_id=order.id,
            product_id=product_id,
            quantity=quantity,
            total=total,
        )
        db.add(order_item)

    await cache.delete_products(product_id)
    await cache.delete_users(order.user_id)
    await cache.delete_orders(order.user_id)

    return {
        "order_id": order.id,
        "user_id": user_db.id,
        "product_id": product_db.id,
        "quantity": quantity,
        "total": float(total),
    }


async def delete_order_db(db: write_db_dependency, order_id):

    async with db.begin():

        result = await db.execute(select(Order).where(Order.id == order_id))
        order = result.scalar_one_or_none()

        if not order:
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

    await cache.delete_products(product_ids)
    await cache.delete_users(order.user_id)
    await cache.delete_orders(order.user_id)

    return {"id": order_id, "message": "Заказ удален"}
