import os
import redis
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from typing import Union, Annotated, AsyncGenerator
from fastapi import Depends
from sqlalchemy.ext.asyncio import (async_sessionmaker, create_async_engine,
                                    AsyncSession, AsyncEngine, AsyncConnection)

load_dotenv()


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


engine = create_async_engine(
    f"postgresql+asyncpg://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@"
    f"{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}")

engine_replica = create_async_engine(
    f"postgresql+asyncpg://{os.getenv('DB_REPLICA_USER')}:{os.getenv('DB_REPLICA_PASSWORD')}@"
    f"{os.getenv('DB_REPLICA_HOST')}:{os.getenv('DB_REPLICA_PORT')}/{os.getenv('DB_REPLICA_NAME')}")

async_session = create_sessionmaker(engine)
async_session_replica = create_sessionmaker(engine_replica)

write_db_dependency = Annotated[AsyncSession, Depends(get_write_session)]
read_db_dependency = Annotated[AsyncSession, Depends(get_read_session)]

redis_client = redis.asyncio.Redis(host=os.getenv('REDIS_HOST'), port=int(os.getenv('REDIS_PORT')),
                                   db=int(os.getenv('REDIS_DB')), decode_responses=True)

mongo_client = AsyncIOMotorClient(os.getenv('MONGO_URI'))
