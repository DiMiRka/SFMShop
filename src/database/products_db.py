from fastapi import HTTPException, status
from sqlalchemy import select, func
from loguru import logger

from src.database.connection import write_db_dependency, read_db_dependency, redis_client
from src.database.models import Product
from src.schemas import ProductCreate, ProductUpdate, ProductResponse
from src.services.cache_service import CacheService

cache = CacheService(redis_client)


async def get_all_products_db(db: read_db_dependency, limit: int, offset: int):
    async def fetch():

        result = await db.execute(select(Product).offset(offset).limit(limit))
        products = result.scalars().all()

        result = await db.execute(select(func.count()).select_from(Product))
        total = result.scalar()

        products_data = [
            ProductResponse.model_validate(product).model_dump(mode="json")
            for product in products
        ]

        response = {
            "total": total,
            "limit": limit,
            "offset": offset,
            "products": products_data,
        }

        return response

    return await cache.get_or_set_cache(f"products:{limit}:{offset}", fetch)


async def get_product_db(db: read_db_dependency, product_id: int):

    async def fetch():
        result = await db.execute(select(Product).where(Product.id == product_id))
        product = result.scalar_one_or_none()

        if not product:
            logger.warning(f"Product id={product_id} not found")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Товар не найден")

        return ProductResponse.model_validate(product).model_dump(mode="json")

    return await cache.get_or_set_cache(f"product:{product_id}", fetch)


async def create_product_db(db: write_db_dependency, product: ProductCreate):
    product_db = Product(**product.model_dump(mode="json"))
    db.add(product_db)
    await db.flush()

    await cache.delete_products()

    return {"id": product_db.id, "message": "Товар добавлен"}


async def update_product_db(db: write_db_dependency, product_id: int, product: ProductUpdate):

    result = await db.execute(select(Product).where(Product.id == product_id))
    product_db = result.scalar_one_or_none()

    if not product_db:
        logger.warning(f"Product id={product_id} not found")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Товар не найден")

    updated_product = product.model_dump(mode="json")

    for field, value in updated_product.items():
        setattr(product_db, field, value)

    await cache.delete_products(product_id)

    return {"id": product_id, "message": "Товар обновлен"}


async def delete_product_db(db: write_db_dependency, product_id):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()

    if not product:
        logger.warning(f"Product id={product_id} not found")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Товар не найден")

    await db.delete(product)

    await cache.delete_products(product_id)

    return {"id": product_id, "message": "Товар удален"}


