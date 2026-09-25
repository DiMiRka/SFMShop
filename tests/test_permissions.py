from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from src.api.main import sfmshop_app as app
from src.core import dependencies


client = TestClient(app)

USER = SimpleNamespace(id=1, is_admin=False)
ADMIN = SimpleNamespace(id=99, is_admin=True)


def teardown_function():
    app.dependency_overrides.clear()


def login_as(user):
    async def override():
        return user

    app.dependency_overrides[dependencies.get_current_user] = override


def use_service(dependency, service):
    async def override():
        return service

    app.dependency_overrides[dependency] = override


def product_service():
    service = MagicMock()
    service.create_product = AsyncMock(return_value={"id": 1, "message": "Товар добавлен"})
    service.update_product = AsyncMock(return_value={"id": 1, "message": "Товар обновлен"})
    service.delete_product = AsyncMock(return_value=None)
    use_service(dependencies.get_product_write_service, service)
    return service


def user_service():
    service = MagicMock()
    service.get_users = AsyncMock(return_value=[])
    service.get_user_by_id = AsyncMock(return_value={"id": 2})
    service.update_user = AsyncMock(return_value={"id": 2, "message": "ok"})
    service.delete_user = AsyncMock(return_value=None)
    service.get_user_orders = AsyncMock(return_value=[])
    use_service(dependencies.get_user_read_service, service)
    use_service(dependencies.get_user_write_service, service)
    return service


PRODUCT = {"name": "Mouse", "price": "10.00", "quantity": 1}


@pytest.mark.parametrize("method, url, body", [
    ("post", "/v1/products/", PRODUCT),
    ("put", "/v1/products/1", {"quantity": 2}),
    ("delete", "/v1/products/1", None),
])
def test_only_admin_can_change_products(method, url, body):
    service = product_service()
    kwargs = {"json": body} if body is not None else {}

    login_as(USER)
    assert client.request(method, url, **kwargs).status_code == 403
    assert not service.method_calls

    login_as(ADMIN)
    assert client.request(method, url, **kwargs).status_code < 300


def test_only_admin_can_list_users():
    service = user_service()

    login_as(USER)
    assert client.get("/v1/users/").status_code == 403
    service.get_users.assert_not_awaited()

    login_as(ADMIN)
    assert client.get("/v1/users/").status_code == 200


@pytest.mark.parametrize("method, url", [
    ("get", "/v1/users/2"),
    ("delete", "/v1/users/2"),
    ("get", "/v1/users/2/orders"),
])
def test_user_cannot_access_another_user(method, url):
    service = user_service()

    login_as(USER)
    assert client.request(method, url).status_code == 403
    assert not service.method_calls

    login_as(ADMIN)
    assert client.request(method, url).status_code < 300


def test_user_can_access_own_profile():
    user_service()
    login_as(USER)

    assert client.get("/v1/users/1").status_code == 200
    assert client.get("/v1/users/1/orders").status_code == 200
    assert client.put("/v1/users/1", json={"name": "New"}).status_code == 200


@pytest.mark.parametrize("field, value", [
    ("balance", 1_000_000),
    ("is_active", False),
    ("is_admin", True),
])
def test_user_cannot_change_admin_only_fields(field, value):
    service = user_service()
    login_as(USER)

    response = client.put("/v1/users/1", json={field: value})

    assert response.status_code == 403
    assert field in response.json()["detail"]
    service.update_user.assert_not_awaited()


def test_admin_can_change_admin_only_fields_of_any_user():
    service = user_service()
    login_as(ADMIN)

    response = client.put("/v1/users/2", json={"balance": 500, "is_admin": True})

    assert response.status_code == 200
    user_id, update = service.update_user.await_args.args
    assert user_id == 2
    assert update.model_dump(exclude_unset=True) == {"balance": 500, "is_admin": True}
