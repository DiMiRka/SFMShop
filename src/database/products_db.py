from fastapi import HTTPException
from sqlalchemy import select

from src.database.connection import db_dependency
from src.database.models import Product
from src.models import Product
from src.schemas import ProductCreate
from src.schemas.products import ProductUpdate


async def get_product_db(db: db_dependency, product_id: int):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()

    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")

    return product


async def add_product_db(db: db_dependency, product: ProductCreate):
    product_db = Product(**product.model_dump())
    db.add(product_db)
    await db.flush()

    return {"id": product.id, "message": "Товар добавлен"}


async def get_all_products_db(db: db_dependency, limit: int, offset: int):
    result = await db.execute(select(Product).offset(offset).limit(limit))
    products = result.scalars().all()
    total = len(products)

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "products": products,
    }


async def update_product_db(db: db_dependency, product_id, product: ProductUpdate):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product_db = result.scalar_one_or_none()

    if not product_db:
        raise HTTPException(status_code=404, detail="Товар не найден")

    updated_product = product.model_dump()

    for field, value in updated_product.items():
        setattr(product_db, field, value)

    return {"id": product_id, "message": "Товар обновлен"}


async def delete_product_db(db: db_dependency, product_id):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()

    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")

    await db.delete(product)

    return {"id": product_id, "message": "Товар удален"}
