from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError as PydanticValidationError

from src.api.exceptions import (
    base_exception_handler,
    business_exception_handler,
    unauthorized_handler,
    validation_exception_handler,
    validation_notfound_handler,
)
from src.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_password_hash,
    verify_password,
)
from src.models.descriptors import AgeDescriptor, CachedProperty, EmailDescriptor, PositiveNumber
from src.models.exceptions import BusinessLogicError, NotFoundError, UnauthorizedError, ValidationError
from src.models.mixins import LoggableMixin, SerializableMixin
from src.models.order import Order, OrderCalculator, OrderValidator
from src.models.product import Product
from src.models.user import User
from src.schemas import (
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
from src.schemas.orders import OrderItemResponse
from src.services.cache_service import CacheService
from src.services.notifications_service import EmailNotification, SMSNotification, send_notification


pytestmark = pytest.mark.anyio


class MemoryRedis:
    def __init__(self):
        self.store = {}
        self.deleted = []
        self.counter = 0

    async def get(self, key):
        return self.store.get(key)

    async def setex(self, key, ttl, value):
        self.store[key] = value
        self.ttl = ttl

    async def incr(self, key):
        self.counter += 1
        return self.counter

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
    assert await cache.get_count("counter") == 1

    redis.store.update({"products:1": b"{}", "users:1": b"{}", "orders:1": b"{}"})
    await cache.delete_products([1, 2])
    await cache.delete_users(3)
    await cache.delete_orders(user_ids=[4], order_ids=5)
    await cache.create_user_session(9, "token")
    assert (await cache.get_user_session("token"))["user_id"] == 9
    await cache.delete_user_session("token")
    assert await cache.get_user_session("missing") is None
    assert "product:1" in redis.deleted
    assert "user:3" in redis.deleted
    assert "order:5" in redis.deleted


def test_descriptors_models_and_mixins(capsys):
    product = Product("Monitor", 100, 2)
    user = User(1, "Dima", "dima@test.com", 31, 1000)
    order = Order(user, [product])

    assert product.to_json() == {"name": "Monitor", "price": 100, "quantity": 2}
    assert user.to_json()["orders_count"] == 0
    assert order.calculate_total() == 200
    assert OrderCalculator.calculate_discount(order, 10) == 180
    assert OrderValidator.validate(order) is True

    with pytest.raises(ValueError):
        Product("Bad", -1, 1)
    with pytest.raises(ValueError):
        User(1, "Bad", "invalid", 18, 10)
    with pytest.raises(ValueError):
        User(1, "Bad", "bad@test.com", 1.5, 10)
    with pytest.raises(ValueError):
        OrderValidator.validate(Order(user, []))
    with pytest.raises(ValueError):
        OrderValidator.validate(Order(None, [product]))

    product._quantity = 0
    with pytest.raises(ValueError):
        OrderValidator.validate(Order(user, [product]))

    class Expensive:
        calls = 0

        @CachedProperty
        def value(self):
            self.calls += 1
            return 5

    item = Expensive()
    assert item.value == 5
    assert item.value == 5
    assert item.calls == 1
    assert isinstance(Expensive.value, CachedProperty)
    assert isinstance(Product.price, PositiveNumber)
    assert isinstance(User.email, EmailDescriptor)
    assert isinstance(User.age, AgeDescriptor)

    LoggableMixin().log("hello")
    assert "hello" in capsys.readouterr().out
    serializable = SerializableMixin()
    serializable.name = "obj"
    assert serializable.to_dict() == {"name": "obj"}
    assert '"name": "obj"' in serializable.to_json()


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
        ProductCreate(name="Desk", price=Decimal("1.00"), quantity=0)

    user = UserCreate(
        name="Dima",
        email="dima@test.com",
        age=31,
        balance=100,
        password="abc12345",
    )
    assert UserInDB(**user.model_dump(), hashed_password="hash").hashed_password == "hash"
    assert UserUpdatePatch(name="New").model_dump(exclude_unset=True) == {"name": "New"}
    assert UserResponse(
        id=1,
        name=user.name,
        email=user.email,
        age=user.age,
        balance=user.balance,
        is_active=True,
        created_at=datetime(2026, 1, 1),
    ).id == 1
    with pytest.raises(PydanticValidationError):
        UserCreate(name="Dima", email="dima@test.com", age=31, balance=100, password="12345678")
    with pytest.raises(PydanticValidationError):
        UserCreate(name="Dima", email="dima@test.com", age=31, balance=100, password="abcdefgh")

    item = OrderItemBase(product_id=1, quantity=2)
    assert OrderItemsInDB(order_id=5, product_id=1, quantity=2, total=Decimal("20.00")).order_id == 5
    assert OrderCreate(user_id=1, items=[item]).items[0].product_id == 1
    assert OrderItemResponse(product_id=1, quantity=2, total=Decimal("20.00")).total == Decimal("20.00")
    assert OrderResponse(
        id=1,
        user_id=1,
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


async def test_notifications_and_api_exception_handlers(capsys):
    assert await EmailNotification().send("hello") == "Email: hello"
    assert "Email: hello" in capsys.readouterr().out
    assert await SMSNotification().send("hello") == "SMS: hello"
    assert await send_notification(SMSNotification(), "hello") is None

    cases = [
        (validation_exception_handler, ValidationError("bad"), 400),
        (validation_notfound_handler, NotFoundError("missing"), 404),
        (unauthorized_handler, UnauthorizedError("no"), 401),
        (business_exception_handler, BusinessLogicError("conflict"), 409),
        (base_exception_handler, Exception("boom"), 500),
    ]
    for handler, exc, status_code in cases:
        response = await handler(None, exc)
        assert response.status_code == status_code
        assert str(exc).encode() in response.body




