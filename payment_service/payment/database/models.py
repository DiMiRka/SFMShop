from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import DECIMAL, CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint, func, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class PaymentStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
    REFUNDED = "refunded"


class TransactionKind(StrEnum):
    TOP_UP = "top_up"
    CHARGE = "charge"
    REFUND = "refund"


def one_of(column: str, values: type[StrEnum]) -> str:
    return f"{column} IN ({', '.join(repr(v.value) for v in values)})"


class Wallet(Base):
    __tablename__ = "wallets"

    user_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    balance: Mapped[Decimal] = mapped_column(
        DECIMAL(12, 2),
        CheckConstraint("balance >= 0", name="check_wallet_balance"),
        nullable=False,
        default=Decimal("0"),
        server_default="0",
    )
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        Index("uq_payments_order_success", "order_id", unique=True, postgresql_where=text("status = 'success'")),
        UniqueConstraint("idempotency_key", name="uq_payments_idempotency_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(
        DECIMAL(10, 2), CheckConstraint("amount > 0", name="check_payment_amount"), nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20), CheckConstraint(one_of("status", PaymentStatus), name="check_payment_status"), nullable=False,
    )
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class WalletTransaction(Base):
    __tablename__ = "wallet_transactions"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_wallet_transactions_idempotency_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("wallets.user_id"), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(
        DECIMAL(12, 2), CheckConstraint("amount <> 0", name="check_transaction_amount"), nullable=False,
    )
    kind: Mapped[str] = mapped_column(
        String(20), CheckConstraint(one_of("kind", TransactionKind), name="check_transaction_kind"), nullable=False,
    )
    payment_id: Mapped[int | None] = mapped_column(ForeignKey("payments.id"))
    idempotency_key: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
