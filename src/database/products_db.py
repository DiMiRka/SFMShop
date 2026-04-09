from fastapi import HTTPException
from sqlalchemy import select, func

from src.database.connection import write_db_dependency, read_db_dependency, redis_client
from src.database.models import Product
from src.schemas import ProductCreate, ProductUpdate, ProductResponse
from src.services.cache_service import CacheService

cache = CacheService(redis_client)


async def get_product_db(db: read_db_dependency, product_id: int):
    if (result := await cache.get(f"product:{product_id}")) is not None:
        return result

    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()

    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")

    product_data = ProductResponse.model_validate(product).model_dump(mode="json")

    await cache.set(f"product:{product_id}", product_data)

    return product_data


async def add_product_db(db: write_db_dependency, product: ProductCreate):
    product_db = Product(**product.model_dump(mode="json"))
    db.add(product_db)
    await db.flush()

    await cache.delete_products()

    return {"id": product_db.id, "message": "Товар добавлен"}


async def get_all_products_db(db: read_db_dependency, limit: int, offset: int):
    try:
        if (result := await cache.get(f"products:{limit}:{offset}")) is not None:
            return result

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

        await cache.set(f"products:{limit}:{offset}", response)

        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при получении товаров: {e}")


async def update_product_db(db: write_db_dependency, product_id, product: ProductUpdate):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product_db = result.scalar_one_or_none()

    if not product_db:
        raise HTTPException(status_code=404, detail="Товар не найден")

    updated_product = product.model_dump(mode="json")

    for field, value in updated_product.items():
        setattr(product_db, field, value)

    await cache.delete_products(product_id)

    return {"id": product_id, "message": "Товар обновлен"}


async def delete_product_db(db: write_db_dependency, product_id):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()

    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")

    await db.delete(product)

    await cache.delete_products(product_id)

    return {"id": product_id, "message": "Товар удален"}
