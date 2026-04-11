from sqlalchemy import select, text
from sqlalchemy.orm import selectinload
from fastapi import HTTPException, status
from loguru import logger

from src.database.connection import write_db_dependency, read_db_dependency, redis_client
from src.database.models import User, Order, OrderItem
from src.schemas import UserResponse, OrderResponse, UserCreate, UserUpdate
from src.models.exceptions import BusinessLogicError
from src.services.cache_service import CacheService

cache = CacheService(redis_client)


async def get_users_db(db: read_db_dependency):

    async def fetch():

        results = await db.execute(select(User))
        users = results.scalars().all()

        users_data = [
            UserResponse.model_validate(user).model_dump(mode="json")
            for user in users
        ]

        return users_data

    return await cache.get_or_set_cache("users", fetch)


async def get_user_by_id_db(db: read_db_dependency, user_id):
    async def fetch():
        results = await db.execute(select(User).where(User.id == user_id))
        user = results.scalar_one_or_none()

        if not user:
            logger.warning(f"User id={user_id} not found")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")

        return UserResponse.model_validate(user).model_dump(mode="json")

    return await cache.get_or_set_cache(f"user:{user_id}", fetch)


async def create_user_db(db: write_db_dependency, user: UserCreate):
    user_db = User(**user.model_dump(mode="json"))
    db.add(user_db)

    await db.flush()

    await cache.delete("users")

    return {"message": f"Пользователь создан id={user_db.id}"}


async def update_user_db(db: write_db_dependency, user_id: int, user: UserUpdate):

    result = await db.execute(select(User).where(User.id == user_id))
    user_db = result.scalar_one_or_none()

    if not user_db:
        logger.warning(f"Product id={user_id} not found")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")

    updated_user = user.model_dump(mode="json")

    for field, value in updated_user.items():
        setattr(user_db, field, value)

    await cache.delete_users(user_id)

    return {"id": user_id, "message": "Пользователь обновлен"}


async def delete_user_db(db: write_db_dependency, user_id: int):
    result = await db.execute(select(User).where(User.id == user_id))
    user_db = result.scalar_one_or_none()

    if not user_db:
        logger.warning(f"User id={user_id} not found")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")

    result = await db.execute(
        select(Order.id).where(Order.user_id == user_id)
    )
    order_ids = result.scalars().all()

    result = await db.execute(
        select(OrderItem.product_id)
        .join(Order, OrderItem.order_id == Order.id)
        .where(Order.user_id == user_id)
    )
    product_ids = result.scalars().all()

    await db.delete(user_db)

    await cache.delete_orders(user_id, order_ids)
    await cache.delete_products(product_ids)
    await cache.delete_users(user_id)

    return {"id": user_id, "message": " Пользователь удален"}


async def get_user_balance_db(db: read_db_dependency, user_id):

    async def fetch():
        result = await db.execute(select(User.balance).where(User.id == user_id))
        balance = result.scalar_one_or_none()

        if balance is None:
            logger.warning(f"User id={user_id} not found")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")

        return balance

    return await cache.get_or_set_cache(f"user_balance:{user_id}", fetch)


async def get_user_email_db(db: read_db_dependency, user_id):

    async def fetch():
        result = await db.execute(select(User.email).where(User.id == user_id))
        email = result.scalar_one_or_none()

        if email is None:
            logger.warning(f"User id={user_id} not found")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")

        return email

    return await cache.get_or_set_cache(f"user_email:{user_id}", fetch)


async def get_user_orders_db(db: read_db_dependency, user_id: int):

    async def fetch():
        result = await db.execute(select(Order).options(selectinload(Order.items)).where(Order.user_id == user_id))
        orders = result.scalars().all()

        orders_data = [
            OrderResponse.model_validate(order).model_dump(mode="json")
            for order in orders
        ]

        return orders_data

    return await cache.get_or_set_cache(f"user_orders:{user_id}", fetch)


async def transfer_money_db(db: write_db_dependency, from_user_id: int, to_user_id: int, amount: int):
    if amount <= 0:
        raise ValueError("Сумма должная быть положительной")

    async with db.begin():
        await db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))

        result = await db.execute(select(User).where(User.id == from_user_id).with_for_update())
        from_user = result.scalar_one_or_none()
        if from_user is None:
            logger.warning(f"User id={from_user_id} not found")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Отправитель не найден")

        if from_user.balance < amount:
            raise BusinessLogicError("Недостаточно средств на балансе")

        result = await db.execute(select(User).where(User.id == to_user_id).with_for_update())
        to_user = result.scalar_one_or_none()
        if to_user is None:
            logger.warning(f"User id={to_user_id} not found")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Получатель не найден")

        from_user.balance -= amount
        to_user.balance += amount

    await cache.delete(
        f"user:{from_user_id}",
        f"user:{to_user_id}",
        f"user_balance:{from_user_id}",
        f"user_balance:{to_user_id}",
        f"users"
    )

    return {"message": "Денежные средства переведены"}
