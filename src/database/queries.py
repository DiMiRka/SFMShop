from psycopg2.extensions import ISOLATION_LEVEL_REPEATABLE_READ, ISOLATION_LEVEL_SERIALIZABLE
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from datetime import datetime

from src.database.connection import db_dependency
from src.database.models import Order, OrderItem, User, Product


async def get_orders_with_products(db: db_dependency, user_id: int):
    result = await db.execute(
        select(Order)
        .options(selectinload(Order.items).selectinload(OrderItem.product))
        .where(Order.user_id == user_id)
    )

    orders = result.scalars().all()

    data = []
    for order in orders:
        for item in order.items:
            data.append({
                "order_id": order.id,
                "product": item.product.name,
                "quantity": item.quantity,
                "price": item.price,
            })

    return data


async def get_orders_count_by_users(db: db_dependency):
    orders_count = func.count(Order.id)

    result = await db.execute(
        select(User.id, User.name, orders_count.label("orders_count"))
        .outerjoin(Order)
        .group_by(User.id, User.name)
        .order_by(orders_count.desc())
    )

    return result.all()


async def get_products_sorted_by_price(db: db_dependency):
    result = await db.execute(select(Product).order_by(Product.price.desc()))

    return result.scalars().all()


async def get_user_order_history(db: db_dependency, user_id):
    result = await db.execute(
        select(
            Order.id.label("order_id"),
            Order.created_at,
            Product.name.label("product_name"),
            Product.price.label("product_price"),
            OrderItem.quantity.label("order_quantity"),
        )
        .join(OrderItem, Order.id == OrderItem.order_id)
        .join(Product, Product.id == OrderItem.product_id)
        .where(Order.user_id == user_id)
        .order_by(Order.created_at.desc())
    )

    orders = result.all()

    print("История заказов пользователя:")
    for order in orders:
        print(order)
    print("------------")
    return orders


async def get_order_statistics(db: db_dependency):
    order_count = func.count(Order.id)
    total_amount = func.coalesce(func.sum(Order.total), 0)

    result = await db.execute(
        select(
            User.id,
            User.name,
            order_count.label("order_count"),
            total_amount.label("total_amount"),
        )
        .outerjoin(Order, User.id == Order.user_id)
        .group_by(User.id, User.name)
        .order_by(total_amount.desc())
    )

    orders = result.all()

    print("Статистика заказов пользователей")
    for row in orders:
        print(row)
    print("------------")

    return orders


async def get_top_products(db: db_dependency, limit=5):
    total_sold = func.coalesce(func.sum(OrderItem.quantity), 0)

    result = await db.execute(
        select(
            Product.id,
            Product.name,
            total_sold.label("total_sold"),
        )
        .join(OrderItem, Product.id == OrderItem.product_id)
        .group_by(Product.id, Product.name)
        .order_by(total_sold.desc())
        .limit(limit)
    )

    products = result.all()

    print("Популярные товары:")
    for row in products:
        print(row)
    print("------------")

    return products


async def generate_sales_report(db: db_dependency, start_date: datetime):
    async with db.connection() as conn:
        await conn.execution_options(isolation_level="REPEATABLE_READ")

    async with db.begin():
        result = await db.execute(
            select(func.coalesce(func.sum(Order.total), 0))
            .where(Order.created_at >= start_date)
        )
        total = result.scalar()

        result = await db.execute(
            select(func.count())
            .select_from(Order)
            .where(Order.created_at >= start_date)
        )
        count = result.scalar()

    return {
        "total": total,
        "count": count,
    }


async def calculate_total_revenue(db: db_dependency, start_date, end_date):
    async with db.connection() as conn:
        await conn.execution_options(isolation_level="REPEATABLE_READ")

    async with db.begin():
        result = await db.execute(
            select(
                func.coalesce(func.sum(Order.total), 0),
                func.count()
            )
            .where(Order.created_at.between(start_date, end_date))
        )

    total, count = result.one()

    return {
        "total": total,
        "count": count,
        "average": float(total) / count if count else None
    }


def create_order_old(conn, user_id, product_id, quantity, total):
    cur = conn.cursor()

    cur.execute("INSERT INTO orders (user_id, total) VALUES (%s, %s)", (user_id, total))
    cur.execute("UPDATE products SET quantity = quantity - %s WHERE id = %s", (quantity, product_id))

    conn.commit()
    conn.close()


def create_order_improved(conn, user_id, product_id, quantity, total):
    conn.set_isolation_level(ISOLATION_LEVEL_REPEATABLE_READ)

    try:
        with conn.cursor() as cur:
            cur.execute("SELECT balance FROM users WHERE id = %s", (user_id,))
            balance = cur.fetchone()[0]
            if balance < total:
                raise ValueError("Недостаточно средств")

            cur.execute("INSERT INTO orders (user_id, total) VALUES (%s, %s)", (user_id, total))
            cur.execute("UPDATE products SET quantity = quantity - %s WHERE id = %s", (quantity, product_id))

            cur.execute("SELECT quantity FROM products WHERE id = %s", (product_id,))
            new_quantity = cur.fetchone()[0]
            if new_quantity < 0:
                raise ValueError("Количество товара стало отрицательным")

            conn.commit()

    except Exception as e:
        conn.rollback()
        raise
