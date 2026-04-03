from fastapi import HTTPException
from sqlalchemy import select

from src.models.exceptions import InsufficientStockError, BusinessLogicError
from src.database.connection import db_dependency
from src.database.models import Order, User, Product, OrderItem


async def create_order_db(db: db_dependency, user_id, product_id, quantity):
    async with db.connection() as conn:
        await conn.execution_options(isolation_level="REPEATABLE_READ")

    async with db.begin():
        result = db.execute(select(Product).where(Product.id == product_id).with_for_update())
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

    return {
        "order_id": order.id,
        "user_id": user_db.id,
        "product_id": product_db.id,
        "quantity": quantity,
        "total": float(total),
    }


async def delete_order_db(db: db_dependency, order_id):
    result = db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(status_code=404, detail="Заказ не найден")
    await db.delete(order)

    return {"id": order_id, "message": "Заказ удален"}
