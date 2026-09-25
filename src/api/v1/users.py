from fastapi import APIRouter, status

from src.schemas import UserUpdatePatch, UserResponse
from src.core.dependencies import admin_user, current_user, user_write_service, user_read_service
from src.core.permissions import ensure_can_update_user, ensure_self_or_admin


users_router = APIRouter(prefix="/users", tags=['users'])


@users_router.get("/", summary="Получить всех пользователей",
                  status_code=status.HTTP_200_OK, response_model=list[UserResponse])
async def get_users(admin: admin_user, service: user_read_service,
                    limit: int = 100, offset: int = 0):
    return await service.get_users(limit, offset)


@users_router.get("/{user_id}", summary="Получить пользователя", status_code=status.HTTP_200_OK)
async def get_user(cu: current_user, service: user_read_service, user_id: int):
    ensure_self_or_admin(cu, user_id)
    return await service.get_user_by_id(user_id)


@users_router.put("/{user_id}", summary="Обновить пользователя", status_code=status.HTTP_200_OK)
async def put_user(cu: current_user, service: user_write_service, user_id: int, user: UserUpdatePatch):
    ensure_can_update_user(cu, user_id, user)
    return await service.update_user(user_id, user)

# Делаем ручку patch


@users_router.delete("/{user_id}", summary="Удалить пользователя", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(cu: current_user, service: user_write_service, user_id: int):
    ensure_self_or_admin(cu, user_id)
    return await service.delete_user(user_id)


@users_router.get("/{user_id}/orders", summary="Получить заказы пользователя", status_code=status.HTTP_200_OK)
async def get_user_orders(cu: current_user, service: user_read_service, user_id: int):
    ensure_self_or_admin(cu, user_id)
    return await service.get_user_orders(user_id)
