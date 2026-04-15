from pydantic import EmailStr, Field, ConfigDict, field_validator
from datetime import datetime
from typing import Optional

from src.schemas.base import Base


class UserBase(Base):
    name: str = Field(..., min_length=1, max_length=20)
    email: EmailStr
    age: int = Field(..., ge=18)
    balance: int = Field(..., ge=0)
    is_active: bool = Field(True)


class UserCreate(UserBase):
    password: str = Field(..., min_length=8, max_length=20)

    @classmethod
    @field_validator('password')
    def validate_password(cls, v: str) -> str:
        if not any(c.isdigit() for c in v):
            raise ValueError(
                "Пароль должен содержать хотя бы одну цифру"
            )
        if not any(c.isalpha() for c in v):
            raise ValueError(
                "Пароль должен содержать хотя бы одну букву"
            )
        return v


class UserInDB(UserBase):
    hashed_password: str


class UserUpdatePatch(Base):
    name: Optional[str] = Field(None, min_length=1, max_length=20)
    password: Optional[str] = Field(None, min_length=8, max_length=20)
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
