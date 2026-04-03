from pydantic import EmailStr, Field, ConfigDict
from datetime import datetime
from typing import Optional

from src.schemas.base import Base


class UserCreate(Base):
    name: str = Field(..., min_length=1, max_length=20)
    email: EmailStr
    age: int = Field(..., ge=18)


class UserUpdate(Base):
    name: Optional[str] = Field(None, min_length=1, max_length=20)
    email: Optional[EmailStr] = None
    age: Optional[int] = Field(None, ge=18)
    balance: Optional[int] = Field(None, ge=0)
    is_active: Optional[bool] = None


class UserResponse(Base):
    id: int
    name: str
    email: EmailStr
    age: int
    balance: int
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
