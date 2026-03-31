from src.schemas.base import Base
from pydantic import Field


class ProductCreate(Base):
    name: str
    price: float
    quantity: int = Field(default=0)
