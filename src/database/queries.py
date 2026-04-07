from sqlalchemy import select, func, text
from sqlalchemy.orm import selectinload
from datetime import datetime

from src.database.connection import read_db_dependency, redis_client
from src.database.models import Order, OrderItem, User, Product
from src.schemas import ProductResponse
from src.services.cache_service import CacheService

cache = CacheService(redis_client)


async def get_orders_with_products(db: read_db_dependency, user_id: int):

    if (result := await cache.get(f"user_orders_products:{user_id}")) is not None:
        return result

    result = await db.execute(
        select(Order)
        .options(selectinload(Order.items).selectinload(OrderItem.product))
        .where(Order.user_id == user_id)
    )

    orders = result.scalars().all()

    data = [
        {"order_id": order.id,
         "product": item.product.name,
         "quantity": item.quantity,
         "price": item.price}
        for order in orders
        for item in order.items
    ]

    await cache.set(f"user_orders_products:{user_id}", data)

    return data


async def get_orders_count_by_users(db: read_db_dependency):

    if (result := await cache.get("orders_count_by_users")) is not None:
        return result

    orders_count = func.count(Order.id)

    result = await db.execute(
        select(User.id, User.name, orders_count.label("orders_count"))
        .outerjoin(Order)
        .group_by(User.id, User.name)
        .order_by(orders_count.desc())
    ).all()

    data = [
        {"user_id": r.id, "name": r.name, "orders_count": r.orders_count}
        for r in result
    ]

    await cache.set("orders_count_by_users", data)

    return data


async def get_products_sorted_by_price(db: read_db_dependency):

    if (result := await cache.get("products_sorted_by_price")) is not None:
        return result

    result = await db.execute(select(Product).order_by(Product.price.desc())).scalars().all()

    data = [
        ProductResponse.model_validate(p).model_dump(mode="json")
        for p in result
    ]

    await cache.set("products_sorted_by_price", data)

    return data


async def get_user_order_history(db: read_db_dependency, user_id):

    if (result := await cache.get(f"user_order_history:{user_id}")) is not None:
        return result

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

    data = [
        {
            "order_id": row.order_id,
            "created_at": row.created_at.isoformat(),
            "product_name": row.product_name,
            "product_price": float(row.product_price),
            "quantity": row.order_quantity
        }
        for row in orders
    ]

    await cache.set(f"user_order_history:{user_id}", data)

    return data


async def get_order_statistics(db: read_db_dependency):

    if (result := await cache.get("order_statistics")) is not None:
        return result

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

    data = [
        {
            "user_id": row.id,
            "name": row.name,
            "order_count": row.order_count,
            "total_amount": float(row.total_amount),
        }
        for row in orders
    ]

    await cache.set("order_statistics", data)

    return data


async def get_top_products(db: read_db_dependency, limit=5):

    if (result := await cache.get(f"top_products:{limit}")) is not None:
        return result

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

    data = [
        {
            "id": row.id,
            "name": row.name,
            "total_sold": row.total_sold
        }
        for row in products
    ]

    await cache.set(f"top_products:{limit}", data)

    return data


async def generate_sales_report(db: read_db_dependency, start_date: datetime):

    if (result := await cache.get(f"sales_report:{start_date}")) is not None:
        return result

    async with db.begin():
        await db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))

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

    response = {
        "total": total,
        "count": count,
    }

    await cache.set(f"sales_report:{start_date}", response)

    return response


async def calculate_total_revenue(db: read_db_dependency, start_date, end_date):

    if (result := await cache.get(f"total_revenue:{start_date}:{end_date}")) is not None:
        return result

    async with db.begin():
        await db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))

        result = await db.execute(
            select(
                func.coalesce(func.sum(Order.total), 0),
                func.count()
            )
            .where(Order.created_at.between(start_date, end_date))
        )

    total, count = result.one()

    response = {
        "total": total,
        "count": count,
        "average": float(total) / count if count else None
    }

    await cache.set(f"total_revenue:{start_date}:{end_date}", response)

    return response
