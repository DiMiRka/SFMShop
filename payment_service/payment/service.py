from decimal import Decimal

from loguru import logger

from payment_service.payment.core.exceptions import ConflictError, IdempotencyKeyReusedError, NotFoundError
from payment_service.payment.database.models import Payment, PaymentStatus, TransactionKind, Wallet, WalletTransaction
from payment_service.payment.repository import PaymentRepository
from payment_service.payment.schemas import ChargeRequest


class PaymentService:
    def __init__(self, repo: PaymentRepository):
        self.repo = repo

    async def charge(self, idempotency_key: str, request: ChargeRequest) -> tuple[Payment, bool]:
        async with self.repo.db.begin():
            wallet = await self.repo.lock_wallet(request.user_id)

            replay = await self.repo.get_payment_by_key(idempotency_key)
            if replay is not None:
                if (replay.order_id, replay.user_id, replay.amount) != (request.order_id, request.user_id, request.amount):
                    raise IdempotencyKeyReusedError("Ключ идемпотентности уже использован с другими параметрами")
                return replay, False

            paid = await self.repo.get_success_payment(request.order_id)
            if paid is not None:
                logger.info(f"Order id={request.order_id} already paid by payment id={paid.id}")
                return paid, False

            payment = Payment(
                order_id=request.order_id,
                user_id=request.user_id,
                amount=request.amount,
                idempotency_key=idempotency_key,
            )

            if wallet.balance >= request.amount:
                wallet.balance -= request.amount
                payment.status = PaymentStatus.SUCCESS
                await self.repo.add(payment)
                await self.repo.add(WalletTransaction(
                    user_id=wallet.user_id, amount=-request.amount, kind=TransactionKind.CHARGE, payment_id=payment.id,
                ))
            else:
                payment.status = PaymentStatus.FAILED
                payment.detail = "Недостаточно средств"
                await self.repo.add(payment)

        return payment, True

    async def refund(self, payment_id: int) -> Payment:
        async with self.repo.db.begin():
            found = await self.repo.get_payment(payment_id)
            if found is None:
                raise NotFoundError("Платёж не найден")

            wallet = await self.repo.lock_wallet(found.user_id)
            payment = await self.repo.lock_payment(payment_id)
            if payment is None:
                raise NotFoundError("Платёж не найден")

            if payment.status == PaymentStatus.REFUNDED:
                return payment
            if payment.status != PaymentStatus.SUCCESS:
                raise ConflictError("Вернуть можно только успешный платёж")

            wallet.balance += payment.amount
            payment.status = PaymentStatus.REFUNDED
            await self.repo.add(WalletTransaction(
                user_id=wallet.user_id, amount=payment.amount, kind=TransactionKind.REFUND, payment_id=payment.id,
            ))

        return payment

    async def top_up(self, idempotency_key: str, user_id: int, amount: Decimal) -> Wallet:
        async with self.repo.db.begin():
            wallet = await self.repo.lock_wallet(user_id)

            replay = await self.repo.get_transaction_by_key(idempotency_key)
            if replay is not None:
                if (replay.user_id, replay.amount, replay.kind) != (user_id, amount, TransactionKind.TOP_UP):
                    raise IdempotencyKeyReusedError("Ключ идемпотентности уже использован с другими параметрами")
                return wallet

            wallet.balance += amount
            await self.repo.add(WalletTransaction(
                user_id=user_id, amount=amount, kind=TransactionKind.TOP_UP, idempotency_key=idempotency_key,
            ))

        return wallet

    async def get_payment(self, payment_id: int) -> Payment:
        payment = await self.repo.get_payment(payment_id)
        if payment is None:
            raise NotFoundError("Платёж не найден")
        return payment

    async def get_balance(self, user_id: int) -> Decimal:
        wallet = await self.repo.get_wallet(user_id)
        return wallet.balance if wallet is not None else Decimal("0.00")
