from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from payment_service.payment.database.connection import get_session
from payment_service.payment.repository import PaymentRepository
from payment_service.payment.service import PaymentService


async def get_payment_service(session: Annotated[AsyncSession, Depends(get_session)]) -> PaymentService:
    return PaymentService(PaymentRepository(session))


payment_service = Annotated[PaymentService, Depends(get_payment_service)]
