from src.schemas.base import Base
from pydantic import Field
from decimal import Decimal


class Product(Base):
    name: str
    price: Decimal
    quantity: int = Field(default=0)
