from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from sfmshop.api.main import sfmshop_app as app
from sfmshop.core import dependencies
from sfmshop.core.exceptions import NotFoundError, PaymentUnavailableError
from sfmshop.services.wallet_service import WalletService
from sfmshop.core.actor import Actor
from tests.test_services import FakePayments, FakeQueue, UserRepoFake


client = TestClient(app)
USER = SimpleNamespace(id=1, is_admin=False, is_active=True)
STRANGER = SimpleNamespace(id=2, is_admin=False, is_active=True)
ADMIN = SimpleNamespace(id=9, is_admin=True, is_active=True)


def teardown_function():
    app.dependency_overrides.clear()


def use(user, payments):
    async def current():
        return user

    queue = FakeQueue()

    async def wallet_service():
        return WalletService(UserRepoFake(), payments, queue)

    app.dependency_overrides[dependencies.get_current_user] = current
    app.dependency_overrides[dependencies.get_wallet_service] = wallet_service
    return queue


@pytest.mark.parametrize("user", [USER, ADMIN])
def test_owner_and_admin_see_balance(user):
    use(user, FakePayments(balance=Decimal("150.50")))

    response = client.get("/v1/users/1/balance")

    assert response.status_code == 200
    assert response.json() == {"user_id": 1, "balance": "150.50"}


def test_stranger_cannot_see_balance():
    use(STRANGER, FakePayments())

    assert client.get("/v1/users/1/balance").status_code == 403


def test_admin_top_up_is_idempotent_by_header():
    payments = FakePayments(balance=Decimal("0.00"))
    queue = use(ADMIN, payments)

    for _ in range(2):
        response = client.post("/v1/users/1/top-up", json={"amount": "250.00"}, headers={"Idempotency-Key": "a-1"})
        assert response.status_code == 200

    assert response.json() == {"user_id": 1, "balance": "250.00"}
    assert payments.top_ups == {"a-1": (1, Decimal("250.00"))}
    event = ("user_exchange", "user.balance_topped_up",
             {"user_ids": 1, "amount": "250.00", "actor_id": 9, "actor_role": "admin"})
    assert queue.events == [event, event]
    assert queue.message_ids == ["top-up-1-a-1", "top-up-1-a-1"]


@pytest.mark.parametrize("user, body, headers, status", [
    (USER, {"amount": "10.00"}, {"Idempotency-Key": "k"}, 403),
    (ADMIN, {"amount": "10.00"}, {}, 422),
    (ADMIN, {"amount": "0"}, {"Idempotency-Key": "k"}, 422),
    (ADMIN, {"amount": "1.001"}, {"Idempotency-Key": "k"}, 422),
    (ADMIN, {"amount": "10.00"}, {"Idempotency-Key": "k" * 65}, 422),
])
def test_top_up_requires_admin_key_and_valid_amount(user, body, headers, status):
    payments = FakePayments()
    use(user, payments)

    response = client.post("/v1/users/1/top-up", json=body, headers=headers)

    assert response.status_code == status
    assert payments.top_ups == {}


def test_unknown_user_and_missing_payment_service():
    use(ADMIN, FakePayments())
    assert client.get("/v1/users/99/balance").status_code == 404

    use(ADMIN, None)
    response = client.get("/v1/users/1/balance")
    assert response.status_code == 503
    assert response.json() == {"detail": "Сервис оплаты не настроен"}


@pytest.mark.anyio
async def test_wallet_service_checks_user_before_calling_payment_service():
    payments, queue = FakePayments(), FakeQueue()
    service = WalletService(UserRepoFake(), payments, queue)

    with pytest.raises(NotFoundError):
        await service.top_up(99, Decimal("1.00"), "k", actor=Actor(9, "admin"))
    assert payments.top_ups == {} and queue.events == []

    with pytest.raises(PaymentUnavailableError):
        await WalletService(UserRepoFake(), None, queue).get_balance(1)
