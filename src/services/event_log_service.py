from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pymongo.errors import PyMongoError

from src.models.exceptions import EventLogUnavailableError
from src.repositories.event_repository import EventRepository
from src.schemas.events import EventFilter, EventResponse
from src.services.log_service import log_service


def to_ids(value: Any) -> list[int]:
    if value is None:
        return []
    if isinstance(value, list):
        return [int(item) for item in value if item is not None]
    return [int(value)]


def build_event(
        routing_key: str,
        payload: dict[str, Any],
        message_id: str | None = None,
        occurred_at: datetime | None = None) -> dict[str, Any]:
    return {
        "_id": message_id or uuid4().hex,
        "event": routing_key,
        "occurred_at": occurred_at or datetime.now(timezone.utc),
        "product_ids": to_ids(payload.get("product_ids")),
        "user_ids": to_ids(payload.get("user_ids")),
        "order_ids": to_ids(payload.get("order_ids")),
        "payload": payload,
    }


class EventLogService:
    def __init__(self, repository: EventRepository):
        self.repository = repository

    async def list_events(self, filters: EventFilter) -> list[EventResponse]:
        try:
            documents = await self.repository.find(filters)
        except PyMongoError as exc:
            log_service.warning("event_log_unavailable", error=repr(exc))
            raise EventLogUnavailableError("Журнал событий временно недоступен") from exc

        return [EventResponse.model_validate({**doc, "id": doc["_id"]}) for doc in documents]
