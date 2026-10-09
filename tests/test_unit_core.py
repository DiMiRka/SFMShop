from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError as PydanticValidationError

from sfmshop.api.exceptions import (
    base_exception_handler,
    business_exception_handler,
    unauthorized_handler,
    validation_exception_handler,
    validation_notfound_handler,
)
from sfmshop.core.config import app_settings
from sfmshop.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_password_hash,
    verify_password,
)
from sfmshop.core.exceptions import BusinessLogicError, NotFoundError, UnauthorizedError, ValidationError
from sfmshop.schemas import (
    OrderCreate,
    OrderItemBase,
    OrderItemsInDB,
    OrderResponse,
    ProductCreate,
    ProductResponse,
    ProductUpdate,
    Token,
    TokenData,
    UserCreate,
    UserInDB,
    UserResponse,
    UserUpdatePatch,
)
from sfmshop.schemas.orders import OrderItemResponse
from sfmshop.services.cache_service import CacheService


pytestmark = pytest.mark.anyio


class MemoryRedis:
    def __init__(self):
        self.store = {}
        self.deleted = []

    async def get(self, key):
        return self.store.get(key)

    async def setex(self, key, ttl, value):
        self.store[key] = value
        self.ttl = ttl

    async def delete(self, *keys):
        self.deleted.extend(keys)
        for key in keys:
            self.store.pop(key, None)

    async def scan_iter(self, pattern, count=100):
        prefix = pattern.rstrip("*")
        for key in list(self.store):
            if key.startswith(prefix):
                yield key


async def test_cache_service_roundtrip_and_invalidation_helpers():
    redis = MemoryRedis()
    cache = CacheService(redis)

    await cache.set("answer", {"value": 42}, ttl=5)
    assert await cache.get("answer") == {"value": 42}
    assert await cache.get("missing") is None

    calls = 0

    async def fetch():
        nonlocal calls
        calls += 1
        return {"fresh": True}

    assert await cache.get_or_set_cache("fresh", fetch) == {"fresh": True}
    assert await cache.get_or_set_cache("fresh", fetch) == {"fresh": True}
    assert calls == 1

    redis.store.update({"products:1": b"{}", "users:1": b"{}", "orders:1": b"{}"})
    await cache.delete_products([1, 2])
    await cache.delete_users(3)
    await cache.delete_orders(user_ids=[4], order_ids=5)
    assert "product:1" in redis.deleted
    assert "user:3" in redis.deleted
    assert "order:5" in redis.deleted


def test_schemas_validate_and_serialize():
    product = ProductCreate(name="Desk", price=Decimal("12.50"), quantity=2)
    assert ProductUpdate(quantity=3).model_dump(exclude_unset=True) == {"quantity": 3}
    assert ProductResponse(
        id=1,
        name=product.name,
        price=product.price,
        quantity=product.quantity,
        created_at=datetime(2026, 1, 1),
    ).model_dump()["id"] == 1

    with pytest.raises(PydanticValidationError):
        ProductCreate(name="", price=Decimal("1.00"), quantity=1)
    with pytest.raises(PydanticValidationError):
        ProductCreate(name="Desk", price=Decimal("1.00"), quantity=-1)

    user = UserCreate(
        name="Dima",
        email="dima@test.com",
        age=31,
        balance=100,
        password="abc12345",
    )
    # Баланс при регистрации игнорируется: новый пользователь всегда начинает с нуля
    user_in_db = UserInDB(**user.model_dump(), hashed_password="hash")
    assert user_in_db.hashed_password == "hash"
    assert user_in_db.balance == 0
    assert user_in_db.is_active is True
    assert UserUpdatePatch(name="New").model_dump(exclude_unset=True) == {"name": "New"}
    assert UserResponse(
        id=1,
        name=user.name,
        email=user.email,
        age=user.age,
        balance=0,
        is_active=True,
        is_admin=False,
        created_at=datetime(2026, 1, 1),
    ).id == 1
    with pytest.raises(PydanticValidationError):
        UserCreate(name="Dima", email="dima@test.com", age=31, password="12345678")
    with pytest.raises(PydanticValidationError):
        UserCreate(name="Dima", email="dima@test.com", age=31, password="abcdefgh")

    item = OrderItemBase(product_id=1, quantity=2)
    assert OrderItemsInDB(order_id=5, product_id=1, quantity=2, total=Decimal("20.00")).order_id == 5
    assert OrderCreate(items=[item]).items[0].product_id == 1
    assert OrderItemResponse(product_id=1, quantity=2, total=Decimal("20.00")).total == Decimal("20.00")
    assert OrderResponse(
        id=1,
        user_id=1,
        status="pending",
        total=Decimal("20.00"),
        created_at=datetime(2026, 1, 1),
        items=[OrderItemResponse(product_id=1, quantity=2, total=Decimal("20.00"))],
    ).items[0].quantity == 2
    assert Token(access_token="a", refresh_token="r").token_type == "bearer"
    assert TokenData(user_id=1).user_id == 1


async def test_security_tokens_and_passwords():
    hashed = await get_password_hash("secret123")
    assert verify_password("secret123", hashed)
    assert not verify_password("bad", hashed)

    access = await create_access_token({"sub": "1"}, expires_delta=timedelta(minutes=5))
    refresh = await create_refresh_token({"sub": "1"})
    assert (await decode_token(access))["sub"] == "1"
    assert (await decode_token(refresh))["sub"] == "1"
    assert await decode_token("not-a-token") is None


async def test_api_exception_handlers():
    cases = [
        (validation_exception_handler, ValidationError("bad"), 400),
        (validation_notfound_handler, NotFoundError("missing"), 404),
        (unauthorized_handler, UnauthorizedError("no"), 401),
        (business_exception_handler, BusinessLogicError("conflict"), 409),
    ]
    for handler, exc, status_code in cases:
        response = await handler(None, exc)
        assert response.status_code == status_code
        assert str(exc).encode() in response.body

    response = await base_exception_handler(None, Exception("boom"))
    assert response.status_code == 500
    assert b"boom" not in response.body


def test_any_email_accepted_by_schema_fits_db_column():
    from sfmshop.database.models import User as DbUser

    local = "a" * 64
    domain = ".".join(["b" * 63, "c" * 63, "d" * 57]) + ".com"
    longest = f"{local}@{domain}"
    assert len(longest) == 254

    user = UserCreate(name="A", email=longest, age=20, password="abc12345")
    assert len(user.email) <= DbUser.__table__.c.email.type.length

    with pytest.raises(PydanticValidationError):
        UserCreate(name="A", email="e" + longest, age=20, password="abc12345")


def test_any_product_name_accepted_by_schema_fits_db_column():
    from sfmshop.database.models import Product as DbProduct

    longest = "x" * 200
    column_length = DbProduct.__table__.c.name.type.length

    assert len(ProductCreate(name=longest, price=Decimal("1.00"), quantity=1).name) <= column_length
    assert len(ProductUpdate(name=longest).name) <= column_length

    with pytest.raises(PydanticValidationError):
        ProductCreate(name=longest + "x", price=Decimal("1.00"), quantity=1)
    with pytest.raises(PydanticValidationError):
        ProductUpdate(name=longest + "x")


@pytest.mark.parametrize("data", [
    {"price": "-1.00"},
    {"price": "0"},
    {"price": "1.001"},
    {"quantity": -1},
    {"name": ""},
    {"name": None},
    {"price": None},
    {"quantity": None},
])
def test_product_update_rejects_invalid_values(data):
    with pytest.raises(PydanticValidationError):
        ProductUpdate.model_validate(data)


def test_product_create_rejects_non_positive_price():
    for price in ("0", "-5.00"):
        with pytest.raises(PydanticValidationError):
            ProductCreate(name="Desk", price=Decimal(price), quantity=1)


def test_product_update_allows_restock_above_create_limit():
    assert ProductUpdate(quantity=150).model_dump(exclude_unset=True) == {"quantity": 150}
    assert ProductUpdate(quantity=0).quantity == 0


def test_user_patch_rejects_explicit_nulls_except_current_password():
    for field in ("name", "email", "age", "balance", "is_active", "is_admin", "password"):
        with pytest.raises(PydanticValidationError):
            UserUpdatePatch.model_validate({field: None})

    assert UserUpdatePatch.model_validate({"name": "New", "current_password": None}).name == "New"


def test_product_response_accepts_existing_zero_price_and_stock():
    from sfmshop.database.models import Product as DbProduct

    product = DbProduct(name="Old", price=Decimal("0.00"), quantity=0)
    product.id = 1
    product.created_at = datetime(2026, 1, 1)

    assert ProductResponse.model_validate(product).price == Decimal("0.00")


async def test_tokens_are_created_without_deprecated_utcnow():
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        access = await create_access_token({"sub": "1"})
        refresh = await create_refresh_token({"sub": "1"})

    now = datetime.now().timestamp()
    access_exp = (await decode_token(access))["exp"]
    refresh_exp = (await decode_token(refresh))["exp"]
    assert abs(access_exp - now - app_settings.access_token_expire_minutes * 60) < 5
    assert abs(refresh_exp - now - app_settings.refresh_token_expire_days * 86400) < 5


def test_product_can_be_created_out_of_stock_or_with_large_stock():
    assert ProductCreate(name="Preorder", price=Decimal("1.00"), quantity=0).quantity == 0
    assert ProductCreate(name="Bulk", price=Decimal("1.00"), quantity=500).quantity == 500


class FlakyRedis(MemoryRedis):
    def __init__(self, fail_get=False, fail_set=False):
        super().__init__()
        self.fail_get = fail_get
        self.fail_set = fail_set
        self.get_calls = 0

    async def get(self, key):
        self.get_calls += 1
        if self.fail_get:
            from redis.exceptions import ConnectionError as RedisConnectionError
            raise RedisConnectionError("redis is down")
        return await super().get(key)

    async def setex(self, key, ttl, value):
        if self.fail_set:
            from redis.exceptions import TimeoutError as RedisTimeoutError
            raise RedisTimeoutError("redis timeout")
        await super().setex(key, ttl, value)

    async def delete(self, *keys):
        from redis.exceptions import ConnectionError as RedisConnectionError
        raise RedisConnectionError("redis is down")


async def test_cache_falls_back_to_database_and_skips_redis_for_a_while(log_messages):
    redis = FlakyRedis(fail_get=True)
    cache = CacheService(redis, retry_after=60)
    loads = []

    async def fetch():
        loads.append(1)
        return {"from": "db"}

    assert await cache.get_or_set_cache("product:1", fetch) == {"from": "db"}
    assert await cache.get_or_set_cache("product:1", fetch) == {"from": "db"}

    assert len(loads) == 2
    assert redis.get_calls == 1
    assert any("cache_unavailable" in message for message in log_messages)


async def test_cache_retries_redis_after_backoff_and_survives_write_errors():
    redis = FlakyRedis(fail_get=True)
    cache = CacheService(redis, retry_after=0)

    async def fetch():
        return {"from": "db"}

    await cache.get_or_set_cache("key", fetch)
    redis.fail_get = False
    redis.fail_set = True
    assert await cache.get_or_set_cache("key", fetch) == {"from": "db"}
    assert redis.get_calls == 2

    redis.fail_set = False
    await cache.get_or_set_cache("key", fetch)
    assert await cache.get("key") == {"from": "db"}


async def test_cache_invalidation_still_fails_loudly_so_event_is_retried():
    from redis.exceptions import RedisError

    with pytest.raises(RedisError):
        await CacheService(FlakyRedis()).delete_products(1)
