from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from payment.database.models import Base, Payment, PaymentStatus, Wallet, WalletTransaction


class PaymentRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_wallet(self, user_id: int) -> Wallet | None:
        return await self.db.get(Wallet, user_id)

    async def lock_wallet(self, user_id: int) -> Wallet:
        await self.db.execute(insert(Wallet).values(user_id=user_id).on_conflict_do_nothing())
        result = await self.db.execute(
            select(Wallet)
            .where(Wallet.user_id == user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return result.scalar_one()

    async def get_payment(self, payment_id: int) -> Payment | None:
        return await self.db.get(Payment, payment_id)

    async def lock_payment(self, payment_id: int) -> Payment | None:
        result = await self.db.execute(
            select(Payment)
            .where(Payment.id == payment_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def get_payment_by_key(self, idempotency_key: str) -> Payment | None:
        result = await self.db.execute(select(Payment).where(Payment.idempotency_key == idempotency_key))
        return result.scalar_one_or_none()

    async def get_success_payment(self, order_id: int) -> Payment | None:
        result = await self.db.execute(
            select(Payment).where(Payment.order_id == order_id, Payment.status == PaymentStatus.SUCCESS)
        )
        return result.scalar_one_or_none()

    async def get_transaction_by_key(self, idempotency_key: str) -> WalletTransaction | None:
        result = await self.db.execute(
            select(WalletTransaction).where(WalletTransaction.idempotency_key == idempotency_key)
        )
        return result.scalar_one_or_none()

    async def add(self, entity: Base) -> None:
        self.db.add(entity)
        await self.db.flush()
