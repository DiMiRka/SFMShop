from decimal import Decimal

from loguru import logger

from payment.core.exceptions import ConflictError, IdempotencyKeyReusedError, NotFoundError
from payment.core.metrics import CHARGED_AMOUNT, CHARGES, REFUNDS, TOP_UPS
from payment.database.models import Payment, PaymentStatus, TransactionKind, Wallet, WalletTransaction
from payment.repository import PaymentRepository
from payment.schemas import ChargeRequest


class PaymentService:
    def __init__(self, repo: PaymentRepository):
        self.repo = repo

    async def charge(self, idempotency_key: str, request: ChargeRequest) -> tuple[Payment, bool]:
        payment, created = await self._charge(idempotency_key, request)

        if not created:
            CHARGES.labels("replay").inc()
        else:
            CHARGES.labels(payment.status).inc()
            if payment.status == PaymentStatus.SUCCESS:
                CHARGED_AMOUNT.inc(float(payment.amount))

        return payment, created

    async def refund(self, payment_id: int) -> Payment:
        payment, refunded = await self._refund(payment_id)
        REFUNDS.labels("refunded" if refunded else "already_refunded").inc()
        return payment

    async def top_up(self, idempotency_key: str, user_id: int, amount: Decimal) -> Wallet:
        wallet, credited = await self._top_up(idempotency_key, user_id, amount)
        TOP_UPS.labels("credited" if credited else "replay").inc()
        return wallet

    async def _charge(self, idempotency_key: str, request: ChargeRequest) -> tuple[Payment, bool]:
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

    async def _refund(self, payment_id: int) -> tuple[Payment, bool]:
        async with self.repo.db.begin():
            found = await self.repo.get_payment(payment_id)
            if found is None:
                raise NotFoundError("Платёж не найден")

            wallet = await self.repo.lock_wallet(found.user_id)
            payment = await self.repo.lock_payment(payment_id)
            if payment is None:
                raise NotFoundError("Платёж не найден")

            if payment.status == PaymentStatus.REFUNDED:
                return payment, False
            if payment.status != PaymentStatus.SUCCESS:
                raise ConflictError("Вернуть можно только успешный платёж")

            wallet.balance += payment.amount
            payment.status = PaymentStatus.REFUNDED
            await self.repo.add(WalletTransaction(
                user_id=wallet.user_id, amount=payment.amount, kind=TransactionKind.REFUND, payment_id=payment.id,
            ))

        return payment, True

    async def _top_up(self, idempotency_key: str, user_id: int, amount: Decimal) -> tuple[Wallet, bool]:
        async with self.repo.db.begin():
            wallet = await self.repo.lock_wallet(user_id)

            replay = await self.repo.get_transaction_by_key(idempotency_key)
            if replay is not None:
                if (replay.user_id, replay.amount, replay.kind) != (user_id, amount, TransactionKind.TOP_UP):
                    raise IdempotencyKeyReusedError("Ключ идемпотентности уже использован с другими параметрами")
                return wallet, False

            wallet.balance += amount
            await self.repo.add(WalletTransaction(
                user_id=user_id, amount=amount, kind=TransactionKind.TOP_UP, idempotency_key=idempotency_key,
            ))

        return wallet, True

    async def get_payment(self, payment_id: int) -> Payment:
        payment = await self.repo.get_payment(payment_id)
        if payment is None:
            raise NotFoundError("Платёж не найден")
        return payment

    async def get_balance(self, user_id: int) -> Decimal:
        wallet = await self.repo.get_wallet(user_id)
        return wallet.balance if wallet is not None else Decimal("0.00")
