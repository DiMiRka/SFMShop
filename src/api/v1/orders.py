from fastapi import APIRouter, HTTPException, status
from loguru import logger
from typing import List

from src.database import (write_db_dependency, read_db_dependency, get_all_orders_db,
                          get_order_by_id_db, create_order_db, delete_order_db)
from src.schemas import OrderCreate, OrderResponse


orders_router = APIRouter(prefix="/orders", tags=['orders'])


@orders_router.get("/", summary="Получить все заказы",
                   response_model=List[OrderResponse], status_code=status.HTTP_200_OK)
async def get_orders(db: read_db_dependency, limit: int = 100, offset: int = 0):
    logger.info(f"get orders limit={limit}, offset={offset}")
    try:
        return await get_all_orders_db(db, limit, offset)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"ERROR get orders limit={limit}, offset={offset}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Ошибка при получении товаров: {e}")


@orders_router.get("/{order_id}", summary="Получить заказ", status_code=status.HTTP_200_OK)
async def get_order(db: read_db_dependency, order_id: int):
    logger.info(f"get order id={order_id}")
    try:
        return await get_order_by_id_db(db, order_id)
    except HTTPException:
        raise
    except Exception:
        logger.exception(f"ERROR get order id={order_id}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Ошибка при получении товара")


@orders_router.post("/", summary="Создать новый заказ", status_code=status.HTTP_201_CREATED)
async def post_order(db: write_db_dependency, order: OrderCreate):
    logger.info(f"create new order")
    try:
        return await create_order_db(db, order)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"ERROR create new order")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Ошибка при создании заказа: {e}")


@orders_router.delete("/", summary="Удалить заказ", status_code=status.HTTP_204_NO_CONTENT)
async def delete_order(db: write_db_dependency, order_id: int):
    logger.info(f"delete order id={order_id}")
    try:
        return await delete_order_db(db, order_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"ERROR delete order id={order_id}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Ошибка при удалении товара: {e}")
