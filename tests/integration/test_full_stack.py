import os
import time
import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from sfmshop.api.main import sfmshop_app as app
from sfmshop.core.config import app_settings
from sfmshop.core.limiter import limiter


pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_INTEGRATION_TESTS"),
    reason="нужны PostgreSQL после миграций, Redis, RabbitMQ и MongoDB (в CI задаётся RUN_INTEGRATION_TESTS=1)",
)

PASSWORD = "abc12345"


@pytest.fixture(scope="module")
def client():
    limiter.reset()
    with TestClient(app) as test_client:
        yield test_client
    limiter.reset()


def unique(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def eventually(check, timeout=15.0, interval=0.3):
    deadline = time.monotonic() + timeout
    while True:
        result = check()
        if result:
            return result
        if time.monotonic() > deadline:
            raise AssertionError("условие не выполнилось за отведённое время")
        time.sleep(interval)


def register(client, name):
    email = f"{unique(name)}@test.com"
    response = client.post("/v1/auth/register", json={"name": name, "email": email, "age": 25, "password": PASSWORD})
    assert response.status_code == 200, response.text
    user = response.json()
    assert user["email"] == email and "hashed_password" not in user
    return user, email


def login(client, email):
    response = client.post("/v1/auth/login", data={"username": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def make_admin(user_id):
    engine = create_engine(app_settings.sync_postgres_url)
    try:
        with engine.begin() as connection:
            connection.execute(text("UPDATE users SET is_admin = true WHERE id = :id"), {"id": user_id})
    finally:
        engine.dispose()


@pytest.fixture(scope="module")
def admin(client):
    user, email = register(client, "admin")
    make_admin(user["id"])
    return login(client, email)


@pytest.fixture(scope="module")
def buyer(client, admin):
    user, email = register(client, "buyer")
    response = client.put(f"/v1/users/{user['id']}", json={"balance": "1000.00"}, headers=admin)
    assert response.status_code == 200, response.text
    return user, login(client, email)


def create_product(client, admin, name=None, price="100.00", quantity=10):
    response = client.post("/v1/products/", json={"name": name or unique("Product"), "price": price,
                                                  "quantity": quantity}, headers=admin)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_app_starts_with_every_dependency_ready(client):
    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "checks": {name: "ok" for name in
                   ("postgres", "postgres_replica", "redis", "rabbitmq", "mongodb", "queue_consumer")},
    }


def test_register_login_and_read_own_profile(client):
    user, email = register(client, "dima")
    headers = login(client, email)

    response = client.get(f"/v1/users/{user['id']}", headers=headers)

    assert response.status_code == 200
    assert response.json()["email"] == email
    assert response.json()["balance"] == "0.00"


def test_price_change_reaches_cache_through_rabbitmq(client, admin):
    product_id = create_product(client, admin, price="100.00")

    assert client.get(f"/v1/products/{product_id}").json()["price"] == "100.00"
    assert client.get(f"/v1/products/{product_id}").json()["price"] == "100.00"

    response = client.put(f"/v1/products/{product_id}", json={"price": "150.00"}, headers=admin)
    assert response.status_code == 200, response.text

    eventually(lambda: client.get(f"/v1/products/{product_id}").json()["price"] == "150.00")


def test_order_charges_balance_reduces_stock_and_lands_in_event_log(client, admin, buyer):
    user, headers = buyer
    product_id = create_product(client, admin, price="120.50", quantity=5)

    response = client.post("/v1/orders/", json={"items": [{"product_id": product_id, "quantity": 2}]}, headers=headers)
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "paid"
    order_id = response.json()["id"]

    assert Decimal(client.get(f"/v1/users/{user['id']}", headers=headers).json()["balance"]) == Decimal("759.00")
    eventually(lambda: client.get(f"/v1/products/{product_id}").json()["quantity"] == 3)

    def logged():
        events = client.get("/v1/events/", params={"event": "order.created", "order_id": order_id}, headers=admin)
        assert events.status_code == 200, events.text
        return events.json()

    [event] = eventually(logged)
    assert event["user_ids"] == [user["id"]] and event["product_ids"] == [product_id]


def test_unpaid_order_fails_then_cancel_returns_stock(client, admin):
    user, email = register(client, "poor")
    headers = login(client, email)
    product_id = create_product(client, admin, price="50.00", quantity=4)

    response = client.post("/v1/orders/", json={"items": [{"product_id": product_id, "quantity": 3}]}, headers=headers)
    assert response.status_code == 201, response.text
    order = response.json()
    assert order["status"] == "failed" and order["total"] == "150.00" and order["created_at"]
    eventually(lambda: client.get(f"/v1/products/{product_id}").json()["quantity"] == 1)

    review = {"rating": 5, "text": "Не оплачен"}
    assert client.post(f"/v1/products/{product_id}/reviews", json=review, headers=headers).status_code == 403

    cancelled = client.post(f"/v1/orders/{order['id']}/cancel", headers=headers)
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"
    assert client.post(f"/v1/orders/{order['id']}/pay", headers=headers).status_code == 409

    eventually(lambda: client.get(f"/v1/products/{product_id}").json()["quantity"] == 4)
    eventually(lambda: client.get(f"/v1/orders/{order['id']}", headers=headers).json()["status"] == "cancelled")


def test_only_buyer_can_review_and_rating_appears_in_card(client, admin, buyer):
    user, headers = buyer
    product_id = create_product(client, admin)
    stranger, stranger_email = register(client, "stranger")

    review = {"rating": 4, "text": "Нормально"}
    assert client.post(f"/v1/products/{product_id}/reviews", json=review,
                       headers=login(client, stranger_email)).status_code == 403

    order = client.post("/v1/orders/", json={"items": [{"product_id": product_id, "quantity": 1}]}, headers=headers)
    assert order.status_code == 201, order.text
    assert client.post(f"/v1/products/{product_id}/reviews", json=review, headers=headers).status_code == 201
    assert client.post(f"/v1/products/{product_id}/reviews", json=review, headers=headers).status_code == 409

    eventually(lambda: client.get(f"/v1/products/{product_id}").json()["reviews_count"] == 1)
    assert client.get(f"/v1/products/{product_id}").json()["average_rating"] == 4.0


def test_product_search_escapes_wildcards_on_real_postgres(client, admin):
    from sfmshop.database.connection import async_session
    from sfmshop.repositories.product_repository import ProductRepository

    marker = uuid.uuid4().hex[:8]
    literal_id = create_product(client, admin, name=f"100%_wool {marker}", price="50.00")
    create_product(client, admin, name=f"100xxwool {marker}", price="50.00")
    create_product(client, admin, name=f"cheap {marker}", price="5.00", quantity=0)

    async def search(**filters):
        async with async_session() as session:
            return [p.id for p in await ProductRepository(session).search(**filters)]

    assert client.portal.call(lambda: search(name_query=f"100%_wool {marker}")) == [literal_id]
    assert len(client.portal.call(lambda: search(name_query=marker))) == 3
    assert len(client.portal.call(lambda: search(name_query=marker, min_price=Decimal("10")))) == 2
    assert len(client.portal.call(lambda: search(name_query=marker, in_stock=True))) == 2
