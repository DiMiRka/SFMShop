from sqlalchemy import select
from fastapi import HTTPException

from src.database.connection import db_dependency
from src.database.models import User, Order
from src.models.exceptions import BusinessLogicError


async def create_user_db(db: db_dependency, name, email, age, balance):
    user = User(name=name, email=email, age=age, balance=balance)
    db.add(user)

    return {"message": "Пользователь создан"}


async def get_users_db(db: db_dependency):
    results = await db.execute(select(User))
    users = results.scalars().all()

    return users


async def get_user_by_id_db(db: db_dependency, user_id):
    results = await db.execute(select(User).where(User.id == user_id))
    user = results.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    return user


async def get_user_balance_db(db: db_dependency, user_id):
    result = await db.execute(select(User.balance).where(User.id == user_id))
    balance = result.scalar_one_or_none()

    if not balance:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    return balance


async def get_user_email_db(db: db_dependency, user_id):
    result = await db.execute(select(User.email).where(User.id == user_id))
    email = result.scalar_one_or_none()

    if not email:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    return email


async def get_user_orders_db(db: db_dependency, user_id: int):
    result = await db.execute(select(Order).where(Order.user_id == user_id))
    orders = result.scalars().all()

    if not orders:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    return orders


async def transfer_money_db(db: db_dependency, from_user_id: int, to_user_id: int, amount: int):
    async with db.connection() as conn:
        await conn.execution_options(isolation_level="REPEATABLE_READ")

    async with db.begin():

        result = await db.execute(select(User).where(User.id == from_user_id).with_for_update())
        from_user = result.scalar_one_or_none()
        if from_user is None:
            raise HTTPException(status_code=404, detail="Отправитель не найден")

        if from_user.balance < amount:
            raise BusinessLogicError("Недостаточно средств на балансе")

        result = await db.execute(select(User).where(User.id == to_user_id).with_for_update())
        to_user = result.scalar_one_or_none()
        if to_user is None:
            raise HTTPException(status_code=404, detail="Получатель не найден")

        from_user.balance -= amount
        to_user.balance += amount

    return {"message": "Денежные средства переведены"}
