from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from src.api.main import sfmshop_app as app
from src.core import dependencies


client = TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


async def override_current_user():
    return SimpleNamespace(id=1)


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

    response = client.post(
        "/v1/orders/",
        json={"user_id": 1, "items": [{"product_id": 2, "quantity": 1}]},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["order_id"] == 42
    assert data["user_id"] == 1
    service.create_order.assert_awaited_once()
