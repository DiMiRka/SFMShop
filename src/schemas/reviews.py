from datetime import datetime
from typing import Optional
from pydantic import ConfigDict, Field

from src.schemas.base import Base, PatchBase


class ReviewCreate(Base):
    rating: int = Field(..., ge=1, le=5)
    text: str = Field(..., min_length=1, max_length=2000)

    model_config = ConfigDict(str_strip_whitespace=True)


class ReviewUpdate(PatchBase):
    rating: Optional[int] = Field(default=None, ge=1, le=5)
    text: Optional[str] = Field(default=None, min_length=1, max_length=2000)

    model_config = ConfigDict(str_strip_whitespace=True)


class ReviewResponse(Base):
    id: int
    product_id: int
    user_id: int
    rating: int
    text: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ReviewList(Base):
    product_id: int
    average_rating: float | None
    reviews_count: int
    limit: int
    offset: int
    reviews: list[ReviewResponse]
