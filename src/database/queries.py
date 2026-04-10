from sqlalchemy import select, func, text
from sqlalchemy.orm import selectinload
from datetime import datetime

from src.database.connection import read_db_dependency, redis_client
from src.database.models import Order, OrderItem, User, Product
from src.schemas import ProductResponse
from src.services.cache_service import CacheService

cache = CacheService(redis_client)


async def get_orders_with_products(db: read_db_dependency, user_id: int):

    async def fetch():
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

        return data

    return await cache.get_or_set_cache(f"user_orders_products:{user_id}", fetch)


async def get_orders_count_by_users(db: read_db_dependency):

    async def fetch():

        orders_count = func.count(Order.id)

        result = await db.execute(
            select(User.id, User.name, orders_count.label("orders_count"))
            .outerjoin(Order)
            .group_by(User.id, User.name)
            .order_by(orders_count.desc())
        )
        orders = result.all()

        data = [
            {"user_id": r.id, "name": r.name, "orders_count": r.orders_count}
            for r in orders
        ]

        return data

    return await cache.get_or_set_cache("orders_count_by_users", fetch)


async def get_products_sorted_by_price(db: read_db_dependency):

    async def fetch():

        result = await db.execute(select(Product).order_by(Product.price.desc()))

        products = result.scalars().all()

        data = [
            ProductResponse.model_validate(p).model_dump(mode="json")
            for p in products
        ]

        return data

    return await cache.get_or_set_cache("products_sorted_by_price", fetch)


async def get_user_order_history(db: read_db_dependency, user_id):

    async def fetch():

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

        return data

    return await cache.get_or_set_cache(f"user_order_history:{user_id}", fetch)


async def get_order_statistics(db: read_db_dependency):

    async def fetch():

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

        return data

    return await cache.get_or_set_cache("order_statistics", fetch)


async def get_top_products(db: read_db_dependency, limit=5):

    async def fetch():

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

        return data

    return await cache.get_or_set_cache(f"top_products:{limit}", fetch)


async def generate_sales_report(db: read_db_dependency, start_date: datetime):

    async def fetch():

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

        return response

    return await cache.get_or_set_cache(f"sales_report:{start_date}", fetch)


async def calculate_total_revenue(db: read_db_dependency, start_date, end_date):

    async def fetch():

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

        return response

    return await cache.get_or_set_cache(f"total_revenue:{start_date}:{end_date}", fetch)
