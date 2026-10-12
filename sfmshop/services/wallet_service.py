from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from loguru import logger

from sfmshop.core.exceptions import NotFoundError, PaymentUnavailableError
from sfmshop.repositories import UserRepository

if TYPE_CHECKING:
    from sfmshop.clients.payment_client import PaymentClient


class WalletService:
    def __init__(self, user_rep: UserRepository, payments: PaymentClient | None):
        self.user_rep = user_rep
        self.payments = payments

    async def get_balance(self, user_id: int) -> dict:
        payments = await self._payments_for(user_id)
        return {"user_id": user_id, "balance": await payments.get_balance(user_id)}

    async def top_up(self, user_id: int, amount: Decimal, idempotency_key: str) -> dict:
        payments = await self._payments_for(user_id)
        balance = await payments.top_up(user_id, amount, idempotency_key)
        logger.info(f"User id={user_id} wallet topped up by {amount}")
        return {"user_id": user_id, "balance": balance}

    async def _payments_for(self, user_id: int) -> PaymentClient:
        if not await self.user_rep.get_by_id(user_id):
            logger.warning(f"User id={user_id} not found")
            raise NotFoundError("Пользователь не найден")

        if self.payments is None:
            raise PaymentUnavailableError("Сервис оплаты не настроен")

        return self.payments
