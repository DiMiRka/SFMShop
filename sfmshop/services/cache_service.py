import time
from redis.asyncio import Redis
from redis.exceptions import RedisError
import orjson
from typing import Any
from loguru import logger

from sfmshop.core.metrics import CACHE_REQUESTS


class CacheService:
    def __init__(self, client: Redis, retry_after: float = 5.0):
        self.redis = client
        self.retry_after = retry_after
        self._unavailable_until = 0.0

    def _available(self) -> bool:
        return time.monotonic() >= self._unavailable_until

    def _mark_unavailable(self, exc: RedisError) -> None:
        self._unavailable_until = time.monotonic() + self.retry_after
        logger.warning(f"cache_unavailable retry_in={self.retry_after} error={exc!r}")

    async def get(self, key: str):
        data = await self.redis.get(key)

        if data:
            return orjson.loads(data)
        return None

    async def set(self, key: str, data: Any, ttl: int = 900):
        data_bytes = orjson.dumps(data)
        await self.redis.setex(key, ttl, data_bytes)

    async def get_or_set_cache(self, key: str, func, ttl: int = 900):
        if not self._available():
            CACHE_REQUESTS.labels("skipped").inc()
        else:
            try:
                cached = await self.get(key)
            except RedisError as exc:
                CACHE_REQUESTS.labels("error").inc()
                self._mark_unavailable(exc)
            else:
                if cached is not None:
                    CACHE_REQUESTS.labels("hit").inc()
                    logger.debug("Данные получены из кэша")
                    return cached
                CACHE_REQUESTS.labels("miss").inc()

        logger.debug("Запрос данных к БД")
        result = await func()

        if self._available():
            try:
                await self.set(key, result, ttl)
            except RedisError as exc:
                self._mark_unavailable(exc)

        return result

    async def delete(self, *keys: str):
        if keys:
            await self.redis.delete(*keys)

    async def delete_many(self, pattern: str, batch_size: int = 100):
        keys = []
        async for key in self.redis.scan_iter(pattern, count=batch_size):
            keys.append(key)
            if len(keys) >= batch_size:
                await self.redis.delete(*keys)
                keys.clear()

        if keys:
            await self.redis.delete(*keys)

    async def delete_products(self, product_ids: int | list[int] | None = None):
        await self.delete_many("products:*")

        if product_ids is not None:
            if isinstance(product_ids, int):
                product_ids = [product_ids]

            await self.delete(*[f"product:{pid}" for pid in product_ids])

    async def delete_users(self, user_ids: int | list[int] | None = None):
        await self.delete_many("users*")

        if user_ids is not None:
            if isinstance(user_ids, int):
                user_ids = [user_ids]

            await self.delete(*[f"user:{user_id}" for user_id in user_ids])

    async def delete_orders(self, user_ids: int | list[int] | None = None, order_ids: int | list[int] | None = None):
        await self.delete_many("orders:*")

        if user_ids is not None:
            if isinstance(user_ids, int):
                user_ids = [user_ids]

            await self.delete(*[f"user_orders:{user_id}" for user_id in user_ids])

        if order_ids is not None:
            if isinstance(order_ids, int):
                order_ids = [order_ids]

            await self.delete(*[f"order:{order_id}" for order_id in order_ids])
