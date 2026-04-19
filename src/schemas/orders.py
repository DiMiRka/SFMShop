from pydantic import ConfigDict
from decimal import Decimal
from datetime import datetime
from typing import List

from src.schemas.base import Base


class OrderItemBase(Base):
    product_id: int
    quantity: int


class OrderItemsInDB(OrderItemBase):
    order_id: int
    total: Decimal


class OrderCreate(Base):
    user_id: int
    items: List[OrderItemBase]


class OrderInDB(OrderCreate):
    total: Decimal


class OrderItemResponse(OrderItemBase):
    total: Decimal

    model_config = ConfigDict(from_attributes=True)


class OrderResponse(Base):
    id: int
    user_id: int
    total: Decimal
    created_at: datetime
    items: List[OrderItemResponse]

    model_config = ConfigDict(from_attributes=True)
