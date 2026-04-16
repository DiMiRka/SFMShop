from fastapi import HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from loguru import logger
import redis.asyncio as redis

from src.models.exceptions import UnauthorizedError
from src.repositories import UserRepository, OrderRepository
from src.services.cache_service import CacheService
from src.schemas import UserCreate, UserInDB, UserUpdatePatch, UserResponse, OrderResponse
from src.core.security import (get_password_hash, verify_password, create_access_token,
                               create_refresh_token, decode_token)
from src.api.exceptions import ValidationError, NotFoundError, UnauthorizedError


class UserService:
    def __init__(
            self,
            user_rep: UserRepository,
            order_rep: OrderRepository,
            client: redis.Redis):
        self.user_rep = user_rep
        self.order_rep = order_rep
        self.cache = CacheService(client)

    async def get_users(self, limit: int, offset: int):
        async def fetch():
            users = await self.user_rep.get_all(limit=limit, offset=offset)

            users_data = [
                UserResponse.model_validate(user).model_dump(mode="json")
                for user in users
            ]

            return users_data

        return await self.cache.get_or_set_cache(f"users:{limit}:{offset}", fetch)

    async def get_user_by_id(self, user_id: int):
        async def fetch():
            user = await self.user_rep.get_by_id(user_id)

            if not user:
                logger.warning(f"User id={user_id} not found")
                raise NotFoundError(f"Пользователь не найден")

            return UserResponse.model_validate(user).model_dump(mode="json")

        return await self.cache.get_or_set_cache(f"user:{user_id}", fetch)

    async def register_user(self, user: UserCreate):
        user_db = await self.user_rep.get_by_email(str(user.email))

        if user_db:
            raise ValidationError("Email уже зарегистрирован")

        hashed_password = get_password_hash(user.password)
        new_user = UserInDB(
            name=user.name,
            email=user.email,
            age=user.age,
            hashed_password=hashed_password
        )
        new_user_db = await self.user_rep.create(new_user.model_dump(mode="json"))

        return {
            "message": "Пользователь создан",
            "user": UserResponse.model_validate(new_user_db).model_dump(mode="json")
        }

    async def authorized_user(self, form_data: OAuth2PasswordRequestForm):
        user = await self.user_rep.get_by_email(form_data.username)

        if not user or not await verify_password(form_data.password, user.hashed_password):
            raise UnauthorizedError("Не верный email или пароль")

        access_token = await create_access_token(data={"sub": str(user.id)})
        refresh_token = await create_refresh_token(data={"sub": str(user.id)})

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer"
        }

    async def create_access_token_db(self, refresh_token: str):
        payload = await decode_token(refresh_token)

        if payload is None:
            raise UnauthorizedError("Неверный refresh token")

        user_id = payload.get("sub")

        if user_id is None:
            raise UnauthorizedError("Неверный refresh token")

        user = await self.user_rep.get_by_id(user_id)

        if user is None:
            raise UnauthorizedError("Пользователь не найден")

        new_access_token = await create_access_token(data={"sub": str(user.id)})

        return {
            "access_token": new_access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer"
        }

    async def update_user(self, user_id: int, user_update: UserUpdatePatch):
        user_db = await self.user_rep.get_by_id(user_id)

        if not user_db:
            logger.warning(f"Product id={user_id} not found")
            raise NotFoundError("Пользователь не найден")

        data = user_update.model_dump(exclude_unset=True)

        await self.user_rep.update(user_db, data)

        await self.cache.delete_users(user_id)

        return {"id": user_id, "message": "Товар обновлен"}

    async def delete_user(self, user_id: int):
        async with self.user_rep.db.begin():
            user_db = await self.user_rep.get_by_id_for_update(user_id)

            if not user_db:
                logger.warning(f"User id={user_id} not found")
                raise NotFoundError("Пользователь не найден")

            order_ids = await self.order_rep.get_order_ids_by_user(user_id)
            product_ids = await self.order_rep.get_product_ids_by_user(user_id)

            await self.user_rep.delete(user_db)

        await self.cache.delete_orders(user_id, order_ids)
        await self.cache.delete_products(product_ids)
        await self.cache.delete_users(user_id)

        return {"id": user_id, "message": " Пользователь удален"}

    async def get_user_balance(self, user_id: int) -> int:
        async def fetch():
            balance = await self.user_rep.get_balance(user_id)

            if balance is None:
                logger.warning(f"User id={user_id} not found")
                raise NotFoundError("Пользователь не найден")

            return balance

        return await self.cache.get_or_set_cache(f"user_balance:{user_id}", fetch)

    async def get_user_email(self, user_id):
        async def fetch():
            email = await self.user_rep.get_email(user_id)

            if email is None:
                logger.warning(f"User id={user_id} not found")
                raise NotFoundError("Пользователь не найден")

            return email

        return await self.cache.get_or_set_cache(f"user_email:{user_id}", fetch)

    async def get_user_orders(self, user_id: int):
        async def fetch():
            orders = await self.order_rep.get_user_orders(user_id)

            orders_data = [
                OrderResponse.model_validate(order).model_dump(mode="json")
                for order in orders
            ]

            return orders_data

        return await self.cache.get_or_set_cache(f"user_orders:{user_id}", fetch)
