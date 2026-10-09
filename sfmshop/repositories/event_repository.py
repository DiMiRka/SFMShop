from typing import Any

from pymongo import ASCENDING, DESCENDING
from pymongo.asynchronous.collection import AsyncCollection

from sfmshop.schemas.events import EventFilter


ENTITY_FIELDS = {"product_id": "product_ids", "user_id": "user_ids", "order_id": "order_ids"}


class EventRepository:
    def __init__(self, collection: AsyncCollection):
        self.collection = collection

    async def ensure_indexes(self, ttl_days: int) -> None:
        await self.collection.create_index(
            [("occurred_at", DESCENDING)], name="occurred_at_ttl", expireAfterSeconds=ttl_days * 86400,
        )
        await self.collection.create_index([("event", ASCENDING), ("occurred_at", DESCENDING)])
        for field in ENTITY_FIELDS.values():
            await self.collection.create_index([(field, ASCENDING), ("occurred_at", DESCENDING)])

    async def add(self, event: dict[str, Any]) -> None:
        fields = {key: value for key, value in event.items() if key != "_id"}
        await self.collection.update_one({"_id": event["_id"]}, {"$setOnInsert": fields}, upsert=True)

    async def find(self, filters: EventFilter) -> list[dict[str, Any]]:
        query: dict[str, Any] = {}
        if filters.event:
            query["event"] = filters.event
        for filter_name, field in ENTITY_FIELDS.items():
            value = getattr(filters, filter_name)
            if value is not None:
                query[field] = value
        if filters.before is not None:
            query["occurred_at"] = {"$lt": filters.before}

        cursor = self.collection.find(query).sort("occurred_at", DESCENDING).limit(filters.limit)
        return await cursor.to_list(length=filters.limit)
