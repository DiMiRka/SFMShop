from fastapi import APIRouter, HTTPException, status, Depends, Response
from loguru import logger
from typing import Optional

from src.services.authorization_service import authorization_user
from src.schemas import ProductCreate, ProductUpdate
from src.database import (read_db_dependency, write_db_dependency, get_all_products_db, get_product_db,
                          create_product_db, update_product_db, delete_product_db)


products_router = APIRouter(prefix="/products", tags=['products'])


@products_router.get("/", summary="Получить все товары", status_code=status.HTTP_200_OK)
async def get_products(db: read_db_dependency, response: Response, _: None = Depends(authorization_user),
                       limit: int = 100, offset: int = 0):

    logger.info(f"get products limit={limit}, offset={offset}")
    response.headers["Cache-Control"] = "max-age=600"

    try:
        return await get_all_products_db(db, limit, offset)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"ERROR get products limit={limit}, offset={offset}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Ошибка при получении товаров: {e}")


@products_router.get("/{product_id}", summary="Получить товар", status_code=status.HTTP_200_OK)
async def get_product(db: read_db_dependency, product_id: int):
    logger.info(f"get product id={product_id}")
    try:
        return await get_product_db(db, product_id)
    except HTTPException:
        raise
    except Exception:
        logger.exception(f"ERROR get product id={product_id}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Ошибка при получении товара")


@products_router.post("/", summary="Создать новый товар", status_code=status.HTTP_201_CREATED)
async def post_product(db: write_db_dependency, product: ProductCreate):
    logger.info(f"create product")
    try:
        return await create_product_db(db, product)
    except Exception as e:
        logger.exception(f"ERROR create product")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Ошибка при создании товара: {e}")


@products_router.put("/{product_id}", summary="Обновить товар", status_code=status.HTTP_200_OK)
async def put_product(db: write_db_dependency, product_id: int, product: ProductUpdate):
    logger.info(f"update product id={product_id}")
    try:
        return await update_product_db(db, product_id, product)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"ERROR update product id={product_id}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Ошибка при обновлении товара: {e}")


@products_router.delete("/{product_id}", summary="Удалить товар", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(db: write_db_dependency, product_id: int):
    logger.info(f"delete product id={product_id}")
    try:
        return await delete_product_db(db, product_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"ERROR delete product id={product_id}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Ошибка при удалении товара: {e}")
