from fastapi import APIRouter, status

from src.schemas import UserUpdate, UserResponse
from src.core.dependencies import write_db_dependency, read_db_dependency, current_user
from src.database import (get_users_db, get_user_by_id_db, update_user_db,
                          delete_user_db, get_user_orders_db)


users_router = APIRouter(prefix="/users", tags=['users'])


@users_router.get("/", summary="Получить всех пользователей",
                  status_code=status.HTTP_200_OK, response_model=UserResponse)
async def get_users(cu: current_user, db: read_db_dependency):
    return await get_users_db(db)


@users_router.get("/{user_id}", summary="Получить пользователя", status_code=status.HTTP_200_OK)
async def get_user(cu: current_user, db: read_db_dependency, user_id: int):
    return await get_user_by_id_db(db, user_id)


@users_router.put("/{user_id}", summary="Обновить пользователя", status_code=status.HTTP_200_OK)
async def put_user(cu: current_user, db: write_db_dependency, user_id: int, user: UserUpdate):
    return await update_user_db(db, user_id, user)

# Делаем ручку patch


@users_router.delete("/{user_id}", summary="Удалить пользователя", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(cu: current_user, db: write_db_dependency, user_id: int):
    return await delete_user_db(db, user_id)


@users_router.get("/{user_id}/orders", summary="Получить заказы пользователя", status_code=status.HTTP_200_OK)
async def get_user_orders(cu: current_user, db: read_db_dependency, user_id: int):
    return get_user_orders_db(db, user_id)
