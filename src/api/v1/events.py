from typing import Annotated

from fastapi import APIRouter, Query, status

from src.core.dependencies import admin_user, event_log_service
from src.schemas.events import EventFilter, EventResponse

events_router = APIRouter(prefix="/events", tags=["events"])


@events_router.get("/", summary="Журнал событий", status_code=status.HTTP_200_OK,
                   response_model=list[EventResponse])
async def get_events(admin: admin_user, service: event_log_service, filters: Annotated[EventFilter, Query()]):
    return await service.list_events(filters)
