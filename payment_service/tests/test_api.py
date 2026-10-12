import pytest


pytestmark = pytest.mark.anyio


async def top_up(client, user_id=10, amount="100.00", key="top-up-1"):
    return await client.post(f"/api/v1/wallets/{user_id}/top-up", json={"amount": amount},
                             headers={"Idempotency-Key": key})


async def charge(client, key="key-1", order_id=1, user_id=10, amount="60.00"):
    return await client.post("/api/v1/payments", json={"order_id": order_id, "user_id": user_id, "amount": amount},
                             headers={"Idempotency-Key": key})


async def test_charge_contract_success_replay_and_detail(client):
    assert (await top_up(client, amount="150.50")).json() == {"user_id": 10, "balance": "150.50"}

    created = await charge(client, amount="150.5")
    assert created.status_code == 201
    assert created.json() == {"id": 1, "order_id": 1, "status": "success"}

    replay = await charge(client, amount="150.50")
    assert replay.status_code == 200
    assert replay.json() == created.json()

    detail = (await client.get("/api/v1/payments/1")).json()
    assert detail["amount"] == "150.50" and detail["user_id"] == 10 and detail["status"] == "success"
    assert (await client.get("/api/v1/wallets/10")).json() == {"user_id": 10, "balance": "0.00"}


async def test_declined_charge_is_409_with_detail(client):
    response = await charge(client)

    assert response.status_code == 409
    assert response.json() == {"id": 1, "order_id": 1, "status": "failed", "detail": "Недостаточно средств"}


async def test_refund_over_http(client):
    await top_up(client)
    await charge(client)

    response = await client.post("/api/v1/payments/1/refund")

    assert response.status_code == 200 and response.json()["status"] == "refunded"
    assert (await client.get("/api/v1/wallets/10")).json()["balance"] == "100.00"
    assert (await client.post("/api/v1/payments/999/refund")).status_code == 404


async def test_domain_errors_map_to_status_codes(client):
    await top_up(client)
    await charge(client, key="key-1", amount="10.00")

    reused = await charge(client, key="key-1", amount="20.00")
    assert reused.status_code == 422
    assert reused.json() == {"detail": "Ключ идемпотентности уже использован с другими параметрами"}

    await charge(client, key="poor", order_id=2, user_id=11)
    assert (await client.post("/api/v1/payments/2/refund")).status_code == 409
    assert (await client.get("/api/v1/payments/999")).status_code == 404


@pytest.mark.parametrize("body", [
    {"order_id": 1, "user_id": 10, "amount": "0"},
    {"order_id": 1, "user_id": 10, "amount": "-5.00"},
    {"order_id": 1, "user_id": 10, "amount": "1.001"},
    {"order_id": 0, "user_id": 10, "amount": "1.00"},
    {"order_id": 1, "amount": "1.00"},
])
async def test_invalid_charge_is_rejected_before_service(client, body, db):
    response = await client.post("/api/v1/payments", json=body, headers={"Idempotency-Key": "k"})

    assert response.status_code == 422
    assert db("SELECT id FROM payments") == []


async def test_idempotency_key_is_required(client):
    response = await client.post("/api/v1/payments", json={"order_id": 1, "user_id": 10, "amount": "1.00"})
    assert response.status_code == 422

    long_key = await charge(client, key="k" * 65)
    assert long_key.status_code == 422


@pytest.mark.parametrize("method, path", [
    ("post", "/api/v1/payments"),
    ("get", "/api/v1/payments/1"),
    ("post", "/api/v1/payments/1/refund"),
    ("get", "/api/v1/wallets/10"),
    ("post", "/api/v1/wallets/10/top-up"),
])
@pytest.mark.parametrize("token", [None, "wrong"])
async def test_every_api_route_requires_service_token(client, method, path, token):
    client.headers.pop("X-Service-Token")
    headers = {"X-Service-Token": token} if token else {}

    response = await client.request(method, path, headers=headers)

    assert response.status_code == 401


async def test_empty_configured_token_rejects_everyone(client, monkeypatch):
    from payment.core import security

    monkeypatch.setattr(security.settings, "service_token", "")
    client.headers["X-Service-Token"] = ""

    assert (await client.get("/api/v1/wallets/10")).status_code == 401


async def test_health_needs_no_token(client):
    client.headers.pop("X-Service-Token")

    assert (await client.get("/health/live")).json() == {"status": "ok"}
    assert (await client.get("/health/ready")).json() == {"status": "ok", "checks": {"postgres": "ok"}}


async def test_ready_is_503_when_database_is_down(client):
    from payment.database.connection import get_session
    from payment.main import app

    class BrokenSession:
        async def execute(self, statement):
            raise ConnectionError("postgres is down")

    async def broken_session():
        yield BrokenSession()

    app.dependency_overrides[get_session] = broken_session
    response = await client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "fail", "checks": {"postgres": "fail"}}


async def test_lifespan_warns_about_empty_token_and_disposes_engine(monkeypatch):
    from loguru import logger

    from payment import main

    class Engine:
        disposed = False

        async def dispose(self):
            self.disposed = True

    engine = Engine()
    messages = []
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(main.settings, "service_token", "")
    monkeypatch.setattr(main.settings, "metrics_port", 9101)
    metrics_ports = []
    monkeypatch.setattr(main, "start_metrics_server", metrics_ports.append)
    handler = logger.add(lambda message: messages.append(message.record["message"]))
    try:
        async with main.lifespan(main.app):
            assert not engine.disposed
    finally:
        logger.remove(handler)

    assert engine.disposed
    assert metrics_ports == [9101]
    assert any("PAYMENT_SERVICE_TOKEN" in message for message in messages)
