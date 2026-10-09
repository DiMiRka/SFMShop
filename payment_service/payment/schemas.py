from datetime import datetime
from decimal import Decimal
from typing import Annotated

from fastapi import Header
from pydantic import BaseModel, ConfigDict, Field

from payment_service.payment.database.models import PaymentStatus


Money = Annotated[Decimal, Field(gt=0, max_digits=10, decimal_places=2)]
IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=64)]


class ChargeRequest(BaseModel):
    order_id: int = Field(gt=0)
    user_id: int = Field(gt=0)
    amount: Money


class PaymentShort(BaseModel):
    id: int
    order_id: int
    status: PaymentStatus

    model_config = ConfigDict(from_attributes=True)


class PaymentDeclined(PaymentShort):
    detail: str


class PaymentDetail(PaymentShort):
    user_id: int
    amount: Decimal
    created_at: datetime


class TopUpRequest(BaseModel):
    amount: Money


class WalletResponse(BaseModel):
    user_id: int
    balance: Decimal

    model_config = ConfigDict(from_attributes=True)
