from pydantic import ConfigDict
from datetime import datetime
from decimal import Decimal
from typing import Optional

from src.schemas.base import Base


class ProductBase(Base):
    name: str
    price: Decimal
    quantity: int = 0


class ProductCreate(ProductBase):
    pass


class ProductUpdate(ProductBase):
    name: Optional[str] = None
    price: Optional[Decimal] = None
    quantity: Optional[int] = None


class ProductResponse(ProductBase):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
