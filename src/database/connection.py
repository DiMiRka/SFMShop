import os
import redis
from dotenv import load_dotenv
from typing import Union, Annotated, AsyncGenerator
from fastapi import Depends
from sqlalchemy.ext.asyncio import (async_sessionmaker, create_async_engine,
                                    AsyncSession, AsyncEngine, AsyncConnection)


load_dotenv()


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def create_sessionmaker(
        bind_engine: Union[AsyncEngine, AsyncConnection]
) -> async_sessionmaker:
    return async_sessionmaker(
        bind=bind_engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )


engine = create_async_engine(f"postgresql+asyncpg://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@"
                             f"{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}")

async_session = create_sessionmaker(engine)

db_dependency = Annotated[AsyncSession, Depends(get_async_session)]

redis_client = redis.asyncio.Redis(host=os.getenv('REDIS_HOST'), port=int(os.getenv('REDIS_PORT')), db=int(os.getenv('REDIS_DB')), decode_responses=True)
