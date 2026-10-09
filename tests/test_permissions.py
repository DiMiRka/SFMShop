from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from sfmshop.api.main import sfmshop_app as app
from sfmshop.core import dependencies
from sfmshop.core.security import pwd_context


client = TestClient(app)

OLD_PASSWORD = "oldpass42"
OLD_HASH = pwd_context.hash(OLD_PASSWORD)
USER = SimpleNamespace(id=1, is_admin=False, hashed_password=OLD_HASH)
ADMIN = SimpleNamespace(id=99, is_admin=True, hashed_password=OLD_HASH)


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


@pytest.mark.parametrize("user, user_id", [(USER, 1), (ADMIN, 99)])
@pytest.mark.parametrize("current_password", [None, "wrongpass1"])
def test_own_password_change_requires_current_password(user, user_id, current_password):
    service = user_service()
    login_as(user)
    body = {"password": "newpass42"}
    if current_password is not None:
        body["current_password"] = current_password

    response = client.put(f"/v1/users/{user_id}", json=body)

    assert response.status_code == 400
    service.update_user.assert_not_awaited()


def test_own_password_change_with_current_password():
    service = user_service()
    login_as(USER)

    response = client.put("/v1/users/1", json={"password": "newpass42", "current_password": OLD_PASSWORD})

    assert response.status_code == 200
    service.update_user.assert_awaited_once()


def test_admin_resets_another_user_password_without_current_password():
    service = user_service()
    login_as(ADMIN)

    response = client.put("/v1/users/2", json={"password": "newpass42"})

    assert response.status_code == 200
    service.update_user.assert_awaited_once()


@pytest.mark.parametrize("body", [
    {"price": None},
    {"name": None},
    {"price": "-10.00"},
    {"quantity": -1},
    {"name": "x" * 201},
])
def test_invalid_product_update_is_rejected_before_service(body):
    service = product_service()
    login_as(ADMIN)

    response = client.put("/v1/products/1", json=body)

    assert response.status_code == 422
    service.update_product.assert_not_awaited()


def test_explicit_null_in_user_update_is_rejected():
    service = user_service()
    login_as(USER)

    response = client.put("/v1/users/1", json={"name": None})

    assert response.status_code == 422
    service.update_user.assert_not_awaited()


def request_with(headers):
    from starlette.requests import Request

    raw = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    return Request({"type": "http", "headers": raw, "client": ("10.0.0.7", 1234)})


@pytest.mark.anyio
async def test_rate_limit_key_uses_verified_user_id_or_falls_back_to_ip():
    from jose import jwt

    from sfmshop.core.limiter import user_or_ip
    from sfmshop.core.security import create_access_token

    token = await create_access_token({"sub": "42"})
    forged = jwt.encode({"sub": "42"}, "not-the-secret", algorithm="HS256")

    assert user_or_ip(request_with({"Authorization": f"Bearer {token}"})) == "user:42"
    assert user_or_ip(request_with({"Authorization": f"Bearer {forged}"})) == "10.0.0.7"
    assert user_or_ip(request_with({"Authorization": "Basic abc"})) == "10.0.0.7"
    assert user_or_ip(request_with({})) == "10.0.0.7"


def test_rate_limit_keeps_working_when_redis_is_down():
    from fastapi import FastAPI, Request
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    from sfmshop.core.limiter import create_limiter

    limiter = create_limiter("redis://127.0.0.1:1/0")
    limited_app = FastAPI()
    limited_app.state.limiter = limiter
    limited_app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    @limited_app.get("/limited")
    @limiter.limit("2/minute")
    async def limited(request: Request):
        return {"ok": True}

    statuses = [TestClient(limited_app).get("/limited").status_code for _ in range(3)]

    assert statuses == [200, 200, 429]


def test_app_limiter_uses_configured_storage():
    from sfmshop.core.config import app_settings
    from sfmshop.core.limiter import limiter

    assert limiter._storage_uri == app_settings.rate_limit_storage_uri
