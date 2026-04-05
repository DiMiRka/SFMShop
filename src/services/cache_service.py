from redis.asyncio import Redis
from datetime import datetime
import json
from typing import Any


class CacheService:
    def __init__(self, client: Redis):
        self.redis = client

    async def get(self, key: str):
        data = await self.redis.get(key)

        if data:
            return json.loads(data)
        return None

    async def set(self, key: str, data: Any, ttl: int = 900):
        await self.redis.setex(key, ttl, json.dumps(data))

    async def delete(self, *keys: str):
        if keys:
            await self.redis.delete(*keys)

    async def delete_many(self, pattern: str, batch_size: int = 100):
        async for key in self.redis.scan_iter(pattern, count=batch_size):
            await self.delete(key)

    async def delete_products(self, product_ids: int | list[int] | None = None):
        await self.delete_many("products:*")
        await self.delete("products_sorted_by_price")

        if product_ids:
            if isinstance(product_ids, int):
                product_ids = [product_ids]

            await self.delete(*[f"product:{pid}" for pid in product_ids])

    async def delete_users(self, user_id):

        await self.delete(
            f"user:{user_id}",
            f"user_balance:{user_id}",
            f"user_email:{user_id}",
            "users"
        )

    async def delete_orders(self, user_id):
        await self.delete_many("top_products:*")
        await self.delete_many("total_revenue:*")
        await self.delete_many("sales_report:*")

        await self.delete(
            f"user_orders_products:{user_id}",
            f"user_order_history:{user_id}",
            f"user_orders:{user_id}",
            "orders_count_by_users",
            "order_statistics"
        )

    async def create_user_session(self, user_id, session_token):
        session_key = f"session:{session_token}"
        session_data = {
            "user_id": user_id,
            "created_at": datetime.now().isoformat()
        }

        await self.set(session_key, session_data, 86400)
        return session_token

    async def get_user_session(self, session_token):
        session_key = f"session:{session_token}"
        cached = await self.get(session_key)
        if cached:
            return cached
        return None

    async def delete_user_session(self, session_token):
        session_key = f"session:{session_token}"
        await self.delete(session_key)
