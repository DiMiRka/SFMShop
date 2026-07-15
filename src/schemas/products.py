from pydantic import ConfigDict, Field
from datetime import datetime
from decimal import Decimal
from typing import Optional

from src.schemas.base import Base


class ProductBase(Base):
    name: str = Field(..., min_length=1, max_length=200)
    price: Decimal = Field(..., max_digits=10, decimal_places=2)
    quantity: int = Field(1, ge=1, le=100)


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
