from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient
from loguru import logger

from src.api.main import sfmshop_app as app
from src.core import dependencies
from src.services.order_service import OrderService


client = TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


async def override_current_user():
    return SimpleNamespace(id=1, is_admin=False)


def test_get_products_with_mocked_service():
    service = MagicMock()
    service.get_all_products = AsyncMock(
        return_value={
            "total": 3,
            "limit": 100,
            "offset": 0,
            "products": [
                {"id": 1, "name": "Laptop", "price": "100000.00", "quantity": 1, "created_at": "2026-01-01T00:00:00"},
                {"id": 2, "name": "Mouse", "price": "1500.00", "quantity": 2, "created_at": "2026-01-01T00:00:00"},
                {"id": 3, "name": "Keyboard", "price": "3000.00", "quantity": 3, "created_at": "2026-01-01T00:00:00"},
            ],
        }
    )

    async def override_product_service():
        return service

    app.dependency_overrides[dependencies.get_product_read_service] = override_product_service

    response = client.get("/v1/products/")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    assert len(data["products"]) == 3
    service.get_all_products.assert_awaited_once_with(100, 0)


def test_unhandled_error_is_hidden_from_client_but_logged(monkeypatch):
    monkeypatch.setattr(app, "debug", False)
    monkeypatch.setattr(app, "middleware_stack", None)
    service = MagicMock()
    service.get_all_products = AsyncMock(side_effect=RuntimeError("connection to db_user:secret@postgres failed"))

    async def override_product_service():
        return service

    app.dependency_overrides[dependencies.get_product_read_service] = override_product_service
    records = []
    handler_id = logger.add(lambda message: records.append(message.record), level="ERROR")
    try:
        response = TestClient(app, raise_server_exceptions=False).get("/v1/products/")
    finally:
        logger.remove(handler_id)

    assert response.status_code == 500
    assert response.json() == {"detail": "Внутренняя ошибка сервера"}
    assert "secret" not in response.text

    failed = [r for r in records if r["message"] == "http_request_failed"]
    assert len(failed) == 1
    assert isinstance(failed[0]["exception"].value, RuntimeError)
    assert failed[0]["extra"]["path"] == "/v1/products/"


def test_create_order_with_mocked_service_and_auth():
    service = MagicMock()
    service.create_order = AsyncMock(
        return_value={
            "order_id": 42,
            "user_id": 1,
            "products_id": [2],
            "quantity": [1],
            "total": 300.0,
        }
    )

    async def override_order_service():
        return service

    app.dependency_overrides[dependencies.get_current_user] = override_current_user
    app.dependency_overrides[dependencies.get_order_write_service] = override_order_service

    # user_id в теле игнорируется: заказ всегда оформляется на текущего пользователя
    response = client.post(
        "/v1/orders/",
        json={"user_id": 2, "items": [{"product_id": 2, "quantity": 1}]},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["order_id"] == 42
    assert data["user_id"] == 1
    service.create_order.assert_awaited_once()
    assert service.create_order.await_args.args[0] == 1


class BeginContext:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class PassThroughCache:
    async def get_or_set_cache(self, key, func, ttl=900):
        return await func()


def build_order_service_with_foreign_order():
    foreign_order = SimpleNamespace(
        id=7, user_id=2, total=Decimal("20.00"), created_at=datetime(2026, 1, 1), items=[]
    )
    order_rep = MagicMock()
    order_rep.db.begin.return_value = BeginContext()
    order_rep.get_by_id = AsyncMock(return_value=foreign_order)
    order_rep.get_by_id_for_update = AsyncMock(return_value=foreign_order)
    order_rep.delete = AsyncMock()
    user_rep = MagicMock()
    user_rep.update = AsyncMock()
    queue = MagicMock()
    queue.publish_event = AsyncMock()

    service = OrderService(order_rep, user_rep, MagicMock(), PassThroughCache(), queue)
    return service, order_rep, user_rep, queue


def test_user_without_orders_gets_empty_list():
    order_rep = MagicMock()
    order_rep.get_user_orders = AsyncMock(return_value=[])
    service = OrderService(order_rep, MagicMock(), MagicMock(), PassThroughCache(), MagicMock())

    async def override_order_service():
        return service

    app.dependency_overrides[dependencies.get_current_user] = override_current_user
    app.dependency_overrides[dependencies.get_order_read_service] = override_order_service

    response = client.get("/v1/orders/")

    assert response.status_code == 200
    assert response.json() == []


def test_foreign_order_is_not_visible_and_cannot_be_deleted():
    service, order_rep, user_rep, queue = build_order_service_with_foreign_order()

    async def override_order_service():
        return service

    app.dependency_overrides[dependencies.get_current_user] = override_current_user
    app.dependency_overrides[dependencies.get_order_read_service] = override_order_service
    app.dependency_overrides[dependencies.get_order_write_service] = override_order_service

    get_response = client.get("/v1/orders/7")
    delete_response = client.delete("/v1/orders/7")

    assert get_response.status_code == 404
    assert delete_response.status_code == 404
    order_rep.delete.assert_not_awaited()
    user_rep.update.assert_not_awaited()
    queue.publish_event.assert_not_awaited()


def test_product_card_is_served_from_database_when_redis_is_down():
    from src.services.cache_service import CacheService
    from src.services.product_service import ProductService
    from tests.test_services import FakeQueue, ProductRepoFake
    from tests.test_unit_core import FlakyRedis

    service = ProductService(ProductRepoFake(), CacheService(FlakyRedis(fail_get=True)), FakeQueue())

    async def override_product_service():
        return service

    app.dependency_overrides[dependencies.get_product_read_service] = override_product_service

    response = client.get("/v1/products/1")

    assert response.status_code == 200
    assert response.json()["name"] == "Mouse"


def test_register_returns_created_user_matching_response_schema():
    from src.services.user_service import UserService
    from tests.test_services import FakeCache, FakeQueue, OrderRepoFake, UserRepoFake

    service = UserService(UserRepoFake(), OrderRepoFake(), FakeCache(), FakeQueue())

    async def override_user_service():
        return service

    app.dependency_overrides[dependencies.get_user_write_service] = override_user_service

    response = TestClient(app, raise_server_exceptions=False).post("/v1/auth/register", json={
        "name": "Dima", "email": "new@test.com", "age": 31, "password": "abc12345",
    })

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "new@test.com" and body["balance"] == "0"
    assert "hashed_password" not in body
