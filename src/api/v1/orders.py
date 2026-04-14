from fastapi import APIRouter, status
from typing import List


from src.schemas import OrderCreate, OrderResponse
from src.core.dependencies import write_db_dependency, read_db_dependency, current_user
from src.database import get_all_orders_db, get_order_by_id_db, create_order_db, delete_order_db


orders_router = APIRouter(prefix="/orders", tags=['orders'])


@orders_router.get("/", summary="Получить все заказы",
                   response_model=List[OrderResponse], status_code=status.HTTP_200_OK)
async def get_orders(cu: current_user, db: read_db_dependency, limit: int = 100, offset: int = 0):
    return await get_all_orders_db(db, limit, offset)


@orders_router.get("/{order_id}", summary="Получить заказ", status_code=status.HTTP_200_OK)
async def get_order(cu: current_user, db: read_db_dependency, order_id: int):
    return await get_order_by_id_db(db, order_id)


@orders_router.post("/", summary="Создать новый заказ", status_code=status.HTTP_201_CREATED)
async def post_order(cu: current_user, db: write_db_dependency, order: OrderCreate):
    return await create_order_db(db, order)


@orders_router.delete("/", summary="Удалить заказ", status_code=status.HTTP_204_NO_CONTENT)
async def delete_order(cu: current_user, db: write_db_dependency, order_id: int):
    return await delete_order_db(db, order_id)
