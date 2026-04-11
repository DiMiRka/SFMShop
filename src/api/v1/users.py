from fastapi import APIRouter, HTTPException, status
from loguru import logger

from src.schemas import UserCreate, UserUpdate
from src.database import (write_db_dependency, read_db_dependency, get_users_db,
                          get_user_by_id_db, create_user_db, update_user_db, delete_user_db,
                          get_user_orders_db)


users_router = APIRouter(prefix="/users", tags=['users'])


@users_router.get("/", summary="Получить всех пользователей", status_code=status.HTTP_200_OK)
async def get_users(db: read_db_dependency):
    logger.info(f"get users")
    try:
        return await get_users_db(db)
    except Exception as e:
        logger.exception(f"ERROR get users")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Ошибка при получении пользователей: {e}")


@users_router.get("/{user_id}", summary="Получить пользователя", status_code=status.HTTP_200_OK)
async def get_user(db: read_db_dependency, user_id: int):
    logger.info(f"get user id={user_id}")
    try:
        return await get_user_by_id_db(db, user_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"ERROR get user id={user_id}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Ошибка при получении пользователя: {e}")


@users_router.post("/", summary="Создать нового пользователя", status_code=status.HTTP_201_CREATED)
async def post_user(db: write_db_dependency, user: UserCreate):
    logger.info(f"create new user")
    try:
        return await create_user_db(db, user)
    except Exception as e:
        logger.exception(f"ERROR create new user")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Ошибка создания пользователя: {e}")


@users_router.put("/{user_id}", summary="Обновить пользователя", status_code=status.HTTP_200_OK)
async def put_user(db: write_db_dependency, user_id: int, user: UserUpdate):
    logger.info(f"update user id={user_id}")
    try:
        return await update_user_db(db, user_id, user)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"ERROR update user id={user_id}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Ошибка при обновлении пользователя: {e}")


@users_router.delete("/{user_id}", summary="Удалить пользователя", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(db: write_db_dependency, user_id: int):
    logger.info(f"delete user id={user_id}")
    try:
        return await delete_user_db(db, user_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"ERROR delete user id={user_id}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Ошибка при удалении пользователя: {e}")


@users_router.get("/{user_id}/orders", summary="Получить заказы пользователя", status_code=status.HTTP_200_OK)
async def get_user_orders(db: read_db_dependency, user_id: int):
    logger.info(f"get user id={user_id} orders")

    try:
        return get_user_orders_db(db, user_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"ERROR get user id={user_id} orders")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Ошибка при получении заказов пользователя: {e}")
