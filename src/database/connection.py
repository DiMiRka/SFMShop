import redis
from motor.motor_asyncio import AsyncIOMotorClient
from typing import Union, Annotated, AsyncGenerator
from fastapi import Depends
from sqlalchemy.ext.asyncio import (async_sessionmaker, create_async_engine,
                                    AsyncSession, AsyncEngine, AsyncConnection)

from src.core.config import app_settings


async def get_write_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_read_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_replica() as session:
        try:
            yield session
        except Exception:
            raise


def create_sessionmaker(
        bind_engine: Union[AsyncEngine, AsyncConnection]
) -> async_sessionmaker:
    return async_sessionmaker(
        bind=bind_engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )


engine = create_async_engine(app_settings.postgres_url)

engine_replica = create_async_engine(app_settings.postgres_replica_url)

async_session = create_sessionmaker(engine)
async_session_replica = create_sessionmaker(engine_replica)

write_db_dependency = Annotated[AsyncSession, Depends(get_write_session)]
read_db_dependency = Annotated[AsyncSession, Depends(get_read_session)]

redis_client = redis.asyncio.Redis.from_url(app_settings.redis_url)

mongo_client = AsyncIOMotorClient(app_settings.mongo_url)
