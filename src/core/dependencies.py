from fastapi import Depends, Request, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import redis
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Annotated

from src.database.models import User
from src.database import get_write_session, get_read_session
from src.services.cache_service import CacheService
from src.services.queue_producer import QueueProducer
from src.services.queue_consumer import QueueConsumer
from src.core.security import decode_token
from src.schemas import TokenData
from src.repositories import ProductRepository, OrderRepository, UserRepository
from src.services import (ProductService, UserService, OrderService, ExchangeRateClient, MultiExchangeClient)


def get_redis(request: Request):
    return request.app.state.redis


redis_dependency = Annotated[redis.asyncio.Redis, Depends(get_redis)]


def get_cache(request: Request):
    return request.app.state.cache


cache_dependency = Annotated[CacheService, Depends(get_cache)]


def get_queue(request: Request):
    return request.app.state.queue


queue_dependency = Annotated[QueueProducer, Depends(get_queue)]


# def get_event_consumer(request: Request) -> QueueConsumer:
#     return request.app.state.consumer
#
#
# consumer_dependency = Annotated[QueueConsumer, Depends(get_event_consumer)]


def get_http_client(request: Request):
    return request.app.state.http_client


http_client_dependency = Annotated[httpx.AsyncClient, Depends(get_http_client)]


# База данных
# ----------------------------------------------------------------------------------------------------------------------
write_db_dependency = Annotated[AsyncSession, Depends(get_write_session)]
read_db_dependency = Annotated[AsyncSession, Depends(get_read_session)]


# Авторизация
# ----------------------------------------------------------------------------------------------------------------------
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/v1/auth/login")


async def get_current_user(db: read_db_dependency, token: str = Depends(oauth2_scheme)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = await decode_token(token)
    if payload is None:
        raise credentials_exception

    user_id = payload.get("sub")
    if user_id is None:
        raise credentials_exception

    token_data = TokenData(user_id=int(user_id))

    results = await db.execute(select(User).where(User.id == token_data.user_id))
    user = results.scalar_one_or_none()

    if user is None:
        raise credentials_exception

    return user


current_user = Annotated[User, Depends(get_current_user)]


# Репозитории
# ----------------------------------------------------------------------------------------------------------------------
async def get_product_write_repository(db: write_db_dependency) -> ProductRepository:
    return ProductRepository(db)


async def get_product_read_repository(db: read_db_dependency) -> ProductRepository:
    return ProductRepository(db)


p_rep_write_dependency = Annotated[ProductRepository, Depends(get_product_write_repository)]
p_rep_read_dependency = Annotated[ProductRepository, Depends(get_product_read_repository)]


async def get_order_write_repository(db: write_db_dependency) -> OrderRepository:
    return OrderRepository(db)


async def get_order_read_repository(db: read_db_dependency) -> OrderRepository:
    return OrderRepository(db)


o_rep_write_dependency = Annotated[OrderRepository, Depends(get_order_write_repository)]
o_rep_read_dependency = Annotated[OrderRepository, Depends(get_order_read_repository)]


async def get_user_write_repository(db: write_db_dependency) -> UserRepository:
    return UserRepository(db)


async def get_user_read_repository(db: read_db_dependency) -> UserRepository:
    return UserRepository(db)


u_rep_write_dependency = Annotated[UserRepository, Depends(get_user_write_repository)]
u_rep_read_dependency = Annotated[UserRepository, Depends(get_user_read_repository)]


# Сервисы
# ----------------------------------------------------------------------------------------------------------------------
async def get_product_write_service(rep: p_rep_write_dependency, cache: cache_dependency, queue: queue_dependency) -> ProductService:
    return ProductService(rep, cache, queue)


async def get_product_read_service(rep: p_rep_read_dependency, cache: cache_dependency, queue: queue_dependency) -> ProductService:
    return ProductService(rep, cache, queue)

product_write_service = Annotated[ProductService, Depends(get_product_write_service)]
product_read_service = Annotated[ProductService, Depends(get_product_read_service)]


async def get_user_write_service(
        u_rep: u_rep_write_dependency,
        o_rep: o_rep_write_dependency,
        cache: cache_dependency,
        queue: queue_dependency) -> UserService:
    return UserService(u_rep, o_rep, cache, queue)


async def get_user_read_service(
        u_rep: u_rep_read_dependency,
        o_rep: o_rep_read_dependency,
        cache: cache_dependency,
        queue: queue_dependency) -> UserService:
    return UserService(u_rep, o_rep, cache, queue)


user_write_service = Annotated[UserService, Depends(get_user_write_service)]
user_read_service = Annotated[UserService, Depends(get_user_read_service)]


async def get_order_write_service(
        o_rep: o_rep_write_dependency,
        u_rep: u_rep_write_dependency,
        p_rep: p_rep_write_dependency,
        cache: cache_dependency,
        queue: queue_dependency
) -> OrderService:
    return OrderService(order_rep=o_rep, user_rep=u_rep, product_rep=p_rep, cache=cache, queue=queue)


async def get_order_read_service(
        o_rep: o_rep_read_dependency,
        u_rep: u_rep_read_dependency,
        p_rep: p_rep_read_dependency,
        cache: cache_dependency,
        queue: queue_dependency
) -> OrderService:
    return OrderService(order_rep=o_rep, user_rep=u_rep, product_rep=p_rep, cache=cache, queue=queue)


order_write_service = Annotated[OrderService, Depends(get_order_write_service)]
order_read_service = Annotated[OrderService, Depends(get_order_read_service)]


# Внешние клиенты
# ----------------------------------------------------------------------------------------------------------------------
async def get_exchange_client():
    client = ExchangeRateClient()
    try:
        yield client
    finally:
        await client.close()


exchange_client = Annotated[ExchangeRateClient, Depends(get_exchange_client)]


async def get_multi_exchange_client():
    client = MultiExchangeClient([
        "https://api.exchangerate-api.com/v4/latest",
        "https://api.currencyapi.com/v3/latest",
        "https://api.fixer.io/latest"
    ])
    try:
        yield client
    finally:
        await client.close()


multi_exchange_client = Annotated[MultiExchangeClient, Depends(get_multi_exchange_client)]
