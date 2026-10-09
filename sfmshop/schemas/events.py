from datetime import datetime

from pydantic import ConfigDict, Field

from sfmshop.schemas.base import Base


class EventFilter(Base):
    event: str | None = Field(None, max_length=50, description="Тип события, например order.created")
    product_id: int | None = Field(None, ge=1)
    user_id: int | None = Field(None, ge=1)
    order_id: int | None = Field(None, ge=1)
    before: datetime | None = Field(None, description="Вернуть события раньше этого момента (для пагинации)")
    limit: int = Field(50, ge=1, le=200)


class EventResponse(Base):
    id: str
    event: str
    occurred_at: datetime
    product_ids: list[int]
    user_ids: list[int]
    order_ids: list[int]
    payload: dict

    model_config = ConfigDict(from_attributes=True)
