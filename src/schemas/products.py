from pydantic import ConfigDict, Field
from datetime import datetime
from decimal import Decimal
from typing import Optional

from src.schemas.base import Base, PatchBase


class ProductBase(Base):
    name: str = Field(..., min_length=1, max_length=200)
    price: Decimal = Field(..., gt=0, max_digits=10, decimal_places=2)
    quantity: int = Field(1, ge=1, le=100)


class ProductCreate(ProductBase):
    pass


class ProductUpdate(PatchBase):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    price: Optional[Decimal] = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    quantity: Optional[int] = Field(default=None, ge=0)


class ProductResponse(ProductBase):
    id: int
    price: Decimal
    quantity: int = Field(..., ge=0)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
