from fastapi import APIRouter, status, Response

from src.schemas import ProductCreate, ProductUpdate
from src.core.dependencies import write_db_dependency, read_db_dependency
from src.core.dependencies import current_user
from src.database import (get_all_products_db, get_product_db, create_product_db, update_product_db, delete_product_db)


products_router = APIRouter(prefix="/products", tags=['products'])


@products_router.get("/", summary="Получить все товары", status_code=status.HTTP_200_OK)
async def get_products(db: read_db_dependency, response: Response,
                       limit: int = 100, offset: int = 0):

    response.headers["Cache-Control"] = "max-age=600"
    return await get_all_products_db(db, limit, offset)


@products_router.get("/{product_id}", summary="Получить товар", status_code=status.HTTP_200_OK)
async def get_product(db: read_db_dependency, product_id: int):
    return await get_product_db(db, product_id)


@products_router.post("/", summary="Создать новый товар", status_code=status.HTTP_201_CREATED)
async def post_product(cu: current_user, db: write_db_dependency, product: ProductCreate):
    return await create_product_db(db, product)


@products_router.put("/{product_id}", summary="Обновить товар", status_code=status.HTTP_200_OK)
async def put_product(cu: current_user, db: write_db_dependency, product_id: int, product: ProductUpdate):
    return await update_product_db(db, product_id, product)


@products_router.delete("/{product_id}", summary="Удалить товар", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(cu: current_user, db: write_db_dependency, product_id: int):
    return await delete_product_db(db, product_id)
