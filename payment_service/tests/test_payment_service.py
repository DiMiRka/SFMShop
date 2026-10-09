import asyncio
from decimal import Decimal

import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from payment.core.exceptions import ConflictError, IdempotencyKeyReusedError, NotFoundError
from payment.database.models import Payment, PaymentStatus
from payment.schemas import ChargeRequest
from tests.conftest import alembic_config


pytestmark = pytest.mark.anyio


def charge(order_id=1, user_id=10, amount="100.00"):
    return ChargeRequest(order_id=order_id, user_id=user_id, amount=Decimal(amount))


async def top_up(service_in, user_id=10, amount="100.00", key=None):
    async with service_in() as service:
        return await service.top_up(key or f"top-up-{user_id}-{amount}", user_id, Decimal(amount))


async def balance(service_in, user_id=10):
    async with service_in() as service:
        return await service.get_balance(user_id)


def ledger(db, user_id=10):
    return [(row.kind, row.amount) for row in db(
        "SELECT kind, amount FROM wallet_transactions WHERE user_id = :user_id ORDER BY id", user_id=user_id)]


async def test_successful_charge_debits_wallet_and_writes_ledger(service_in, db):
    await top_up(service_in, amount="150.50")

    async with service_in() as service:
        payment, created = await service.charge("key-1", charge(amount="100.25"))

    assert created and payment.status == PaymentStatus.SUCCESS
    assert await balance(service_in) == Decimal("50.25")
    assert ledger(db) == [("top_up", Decimal("150.50")), ("charge", Decimal("-100.25"))]


async def test_insufficient_funds_saves_failed_payment_without_touching_wallet(service_in, db):
    await top_up(service_in, amount="10.00")

    async with service_in() as service:
        payment, created = await service.charge("key-1", charge(amount="10.01"))

    assert created and payment.status == PaymentStatus.FAILED
    assert payment.detail == "Недостаточно средств"
    assert await balance(service_in) == Decimal("10.00")
    assert ledger(db) == [("top_up", Decimal("10.00"))]


async def test_unknown_user_has_empty_wallet(service_in, db):
    assert await balance(service_in, user_id=99) == Decimal("0.00")
    assert db("SELECT user_id FROM wallets") == []

    async with service_in() as service:
        payment, _ = await service.charge("key-1", charge(user_id=99))

    assert payment.status == PaymentStatus.FAILED


async def test_replay_with_same_key_returns_same_payment_without_second_debit(service_in):
    await top_up(service_in, amount="300.00")

    async with service_in() as service:
        first, _ = await service.charge("key-1", charge())
    async with service_in() as service:
        replay, created = await service.charge("key-1", charge())

    assert not created and replay.id == first.id
    assert await balance(service_in) == Decimal("200.00")


async def test_same_key_with_other_request_is_rejected(service_in):
    await top_up(service_in)
    async with service_in() as service:
        await service.charge("key-1", charge(amount="10.00"))

    with pytest.raises(IdempotencyKeyReusedError):
        async with service_in() as service:
            await service.charge("key-1", charge(amount="20.00"))


async def test_paid_order_is_not_charged_again_with_new_key(service_in):
    await top_up(service_in, amount="300.00")
    async with service_in() as service:
        first, _ = await service.charge("key-1", charge())
    async with service_in() as service:
        second, created = await service.charge("key-2", charge())

    assert not created and second.id == first.id
    assert await balance(service_in) == Decimal("200.00")


async def test_failed_order_can_be_paid_after_top_up_with_new_key(service_in, db):
    async with service_in() as service:
        failed, _ = await service.charge("key-1", charge())
    await top_up(service_in, amount="100.00")
    async with service_in() as service:
        paid, created = await service.charge("key-2", charge())

    assert failed.status == PaymentStatus.FAILED
    assert created and paid.status == PaymentStatus.SUCCESS
    assert [row.status for row in db("SELECT status FROM payments WHERE order_id = 1 ORDER BY id")] == [
        "failed", "success"]


async def test_concurrent_charges_for_one_order_debit_once(service_in, db):
    await top_up(service_in, amount="1000.00")

    async def pay(key):
        async with service_in() as service:
            payment, _ = await service.charge(key, charge())
            return payment.id

    ids = await asyncio.gather(*(pay(f"key-{i}") for i in range(5)))

    assert len(set(ids)) == 1
    assert await balance(service_in) == Decimal("900.00")
    assert len(db("SELECT id FROM payments")) == 1


async def test_concurrent_charges_never_overdraw_wallet(service_in, db):
    await top_up(service_in, amount="250.00")

    async def pay(order_id):
        async with service_in() as service:
            payment, _ = await service.charge(f"key-{order_id}", charge(order_id=order_id))
            return payment.status

    statuses = await asyncio.gather(*(pay(order_id) for order_id in range(1, 6)))

    assert sorted(statuses) == ["failed", "failed", "failed", "success", "success"]
    assert await balance(service_in) == Decimal("50.00")
    [(total,)] = db("SELECT sum(amount) FROM wallet_transactions WHERE user_id = 10")
    assert total == Decimal("50.00")


async def test_refund_returns_money_once(service_in, db):
    await top_up(service_in, amount="100.00")
    async with service_in() as service:
        payment, _ = await service.charge("key-1", charge(amount="60.00"))

    for _ in range(2):
        async with service_in() as service:
            refunded = await service.refund(payment.id)
        assert refunded.status == PaymentStatus.REFUNDED

    assert await balance(service_in) == Decimal("100.00")
    assert ledger(db)[-1] == ("refund", Decimal("60.00"))
    assert len(ledger(db)) == 3


async def test_refunded_order_can_be_paid_again(service_in):
    await top_up(service_in, amount="100.00")
    async with service_in() as service:
        payment, _ = await service.charge("key-1", charge(amount="60.00"))
    async with service_in() as service:
        await service.refund(payment.id)
    async with service_in() as service:
        again, created = await service.charge("key-2", charge(amount="60.00"))

    assert created and again.status == PaymentStatus.SUCCESS


async def test_only_successful_payment_can_be_refunded(service_in):
    async with service_in() as service:
        failed, _ = await service.charge("key-1", charge())

    with pytest.raises(ConflictError):
        async with service_in() as service:
            await service.refund(failed.id)
    with pytest.raises(NotFoundError):
        async with service_in() as service:
            await service.refund(999)


async def test_top_up_is_idempotent_by_key(service_in, db):
    await top_up(service_in, amount="50.00", key="admin-1")
    await top_up(service_in, amount="50.00", key="admin-1")

    assert await balance(service_in) == Decimal("50.00")
    with pytest.raises(IdempotencyKeyReusedError):
        await top_up(service_in, amount="70.00", key="admin-1")
    with pytest.raises(IdempotencyKeyReusedError):
        await top_up(service_in, user_id=11, amount="50.00", key="admin-1")


async def test_database_rejects_second_successful_payment_for_order(service_in, session_factory):
    async with session_factory() as session:
        session.add_all([
            Payment(order_id=1, user_id=10, amount=Decimal("1.00"), status="success", idempotency_key="a"),
            Payment(order_id=1, user_id=10, amount=Decimal("1.00"), status="success", idempotency_key="b"),
        ])
        with pytest.raises(IntegrityError, match="uq_payments_order_success"):
            await session.commit()


def test_database_rejects_negative_balance(sync_engine):
    with pytest.raises(IntegrityError, match="check_wallet_balance"):
        with sync_engine.begin() as connection:
            connection.execute(text("INSERT INTO wallets (user_id, balance) VALUES (1, -1)"))


def test_migrations_match_models(sync_engine):
    command.check(alembic_config())


def test_migrations_downgrade_and_upgrade_again(sync_engine):
    config = alembic_config()
    command.downgrade(config, "base")
    command.upgrade(config, "head")
