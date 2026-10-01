from pydantic import EmailStr, Field, ConfigDict, field_validator
from datetime import datetime
from decimal import Decimal
from typing import Optional

from src.schemas.base import Base


class UserBase(Base):
    name: str = Field(..., min_length=1, max_length=20)
    email: EmailStr
    age: int = Field(..., ge=18)


class UserCreate(UserBase):
    password: str = Field(..., min_length=8, max_length=20)

    @field_validator('password')
    @classmethod
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
    balance: Decimal = Field(default=Decimal("0"), ge=0, max_digits=10, decimal_places=2)
    is_active: bool = True


ADMIN_ONLY_USER_FIELDS = frozenset({"balance", "is_active", "is_admin"})


class UserUpdatePatch(Base):
    name: Optional[str] = Field(default=None, min_length=1, max_length=20)
    password: Optional[str] = Field(default=None, min_length=8, max_length=20)
    current_password: Optional[str] = None
    email: Optional[EmailStr] = None
    age: Optional[int] = Field(default=None, ge=18)
    balance: Optional[Decimal] = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    is_active: Optional[bool] = None
    is_admin: Optional[bool] = None

    @field_validator('password')
    @classmethod
    def validate_password(cls, v: Optional[str]) -> Optional[str]:
        return v if v is None else UserCreate.validate_password(v)


class UserResponse(Base):
    id: int
    name: str
    email: EmailStr
    age: int
    balance: Decimal
    is_active: bool
    is_admin: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
