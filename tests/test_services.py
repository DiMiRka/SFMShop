from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from src.models.exceptions import BusinessLogicError, NotFoundError, UnauthorizedError, ValidationError
from src.database.models import Product as DbProduct, User as DbUser
from src.schemas import OrderCreate, OrderItemBase, ProductCreate, ProductUpdate, UserCreate, UserUpdatePatch
from src.core.security import get_password_hash
from src.services.order_service import OrderService
from src.services.product_service import ProductService
from src.services.user_service import UserService


pytestmark = pytest.mark.anyio


class BeginContext:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeDb:
    def begin(self):
        return BeginContext()


class FakeCache:
    def __init__(self):
        self.calls = []

    async def get_or_set_cache(self, key, func, ttl=900):
        self.calls.append((key, ttl))
        return await func()


class FakeQueue:
    def __init__(self):
        self.events = []

    async def publish_event(self, exchange, routing_key, message):
        self.events.append((exchange, routing_key, message))
        return True


def db_product(product_id=1, name="Mouse", price=Decimal("10.00"), quantity=5):
    product = DbProduct(name=name, price=price, quantity=quantity)
    product.id = product_id
    product.created_at = datetime(2026, 1, 1)
    return product


def db_user(user_id=1, name="Dima", email="dima@test.com", balance=Decimal("100.00")):
    user = DbUser(name=name, email=email, age=30, balance=balance, hashed_password="hash", is_active=True)
    user.id = user_id
    user.created_at = datetime(2026, 1, 1)
    return user


class ProductRepoFake:
    def __init__(self):
        self.db = FakeDb()
        self.product = db_product()
        self.products = [self.product]
        self.updated = None
        self.deleted = None

    async def get_all(self, limit=100, offset=0):
        self.last_page = (limit, offset)
        return self.products

    async def get_count_all(self):
        return len(self.products)

    async def get_by_id(self, product_id):
        return self.product if product_id == self.product.id else None

    async def get_by_ids(self, ids):
        return [p for p in self.products if p.id in ids]

    async def get_by_ids_for_update(self, ids):
        return await self.get_by_ids(ids)

    async def create(self, data):
        self.created = data
        return 44

    async def update(self, product, data):
        self.updated = (product, data)
        for field, value in data.items():
            setattr(product, field, value)

    async def delete(self, product):
        self.deleted = product


class UserRepoFake:
    def __init__(self):
        self.db = FakeDb()
        self.user = db_user()
        self.email_user = None
        self.updated = None
        self.deleted = None

    async def get_all(self, limit=100, offset=0):
        return [self.user]

    async def get_by_id(self, user_id):
        return self.user if self.user is not None and int(user_id) == self.user.id else None

    async def get_by_id_for_update(self, user_id):
        return await self.get_by_id(user_id)

    async def get_by_email(self, email):
        return self.email_user

    async def create(self, data):
        self.created = data
        return db_user(2, data["name"], data["email"], Decimal(str(data["balance"])))

    async def update(self, user, data):
        self.updated = (user, data)
        for field, value in data.items():
            setattr(user, field, value)

    async def delete(self, user):
        self.deleted = user

    async def get_balance(self, user_id):
        return self.user.balance if self.user is not None and user_id == self.user.id else None

    async def get_email(self, user_id):
        return self.user.email if self.user is not None and user_id == self.user.id else None


class OrderRepoFake:
    def __init__(self):
        self.db = FakeDb()
        item = SimpleNamespace(id=10, product_id=1, quantity=2, total=Decimal("20.00"))
        self.order = SimpleNamespace(
            id=7,
            user_id=1,
            total=Decimal("20.00"),
            created_at=datetime(2026, 1, 1),
            items=[item],
        )
        self.created_items = []
        self.deleted = None

    async def get_all(self, limit=100, offset=0):
        return [self.order]

    async def get_by_id(self, order_id):
        return self.order if order_id == self.order.id else None

    async def get_by_id_for_update(self, order_id):
        return await self.get_by_id(order_id)

    async def get_user_orders(self, user_id):
        return [self.order] if user_id == self.order.user_id else []

    async def get_order_ids_by_user(self, user_id):
        return [self.order.id] if user_id == self.order.user_id else None

    async def get_product_ids_by_user(self, user_id):
        return [1] if user_id == self.order.user_id else None

    async def get_order_products(self, order_id):
        return self.order.items if order_id == self.order.id else []

    async def create(self, data):
        self.created = data
        return 77

    async def create_order_item(self, data):
        self.created_items.append(data)
        return data

    async def delete(self, order):
        self.deleted = order


async def test_product_service_success_and_not_found():
    repo = ProductRepoFake()
    queue = FakeQueue()
    service = ProductService(repo, FakeCache(), queue)

    all_products = await service.get_all_products(10, 5)
    assert all_products["total"] == 1
    assert all_products["products"][0]["id"] == 1
    assert (await service.get_product_by_id(1))["name"] == "Mouse"
    assert await service.create_product(ProductCreate(name="New", price=Decimal("1.00"), quantity=1)) == {
        "id": 44,
        "message": "Товар добавлен",
    }
    assert await service.update_product(1, ProductUpdate(quantity=4)) == {
        "id": 1,
        "message": "Товар обновлен",
    }
    assert repo.updated[1] == {"quantity": 4}
    assert await service.delete_product(1) == {"id": 1, "message": "Товар удален"}
    assert queue.events[-1][1] == "product.deleted"

    with pytest.raises(NotFoundError):
        await service.get_product_by_id(999)
    with pytest.raises(NotFoundError):
        await service.update_product(999, ProductUpdate(quantity=2))
    with pytest.raises(NotFoundError):
        await service.delete_product(999)


async def test_user_service_success_auth_and_not_found():
    users = UserRepoFake()
    orders = OrderRepoFake()
    queue = FakeQueue()
    service = UserService(users, orders, FakeCache(), queue)

    assert (await service.get_users(10, 0))[0]["email"] == "dima@test.com"
    assert (await service.get_user_by_id(1))["id"] == 1
    registered = await service.register_user(
        UserCreate(name="New", email="new@test.com", age=22, balance=50, password="abc12345")
    )
    assert registered["user"]["email"] == "new@test.com"
    assert users.created["balance"] == 50

    users.email_user = users.user
    with pytest.raises(ValidationError):
        await service.register_user(
            UserCreate(name="New", email="dima@test.com", age=22, balance=50, password="abc12345")
        )

    users.user.hashed_password = await get_password_hash("abc12345")
    form = SimpleNamespace(username="dima@test.com", password="abc12345")
    tokens = await service.authorized_user(form)
    assert tokens["token_type"] == "bearer"
    assert (await service.create_access_token_db(tokens["refresh_token"]))["access_token"]

    bad_form = SimpleNamespace(username="dima@test.com", password="wrong")
    with pytest.raises(UnauthorizedError):
        await service.authorized_user(bad_form)
    with pytest.raises(UnauthorizedError):
        await service.create_access_token_db("bad")

    assert await service.update_user(1, UserUpdatePatch(name="Updated")) == {
        "id": 1,
        "message": "Товар обновлен",
    }
    assert await service.delete_user(1) == {"id": 1, "message": " Пользователь удален"}
    assert await service.get_user_balance(1) == Decimal("100.00")
    assert await service.get_user_email(1) == "dima@test.com"
    assert (await service.get_user_orders(1))[0]["id"] == 7

    with pytest.raises(NotFoundError):
        await service.get_user_by_id(999)
    with pytest.raises(NotFoundError):
        await service.update_user(999, UserUpdatePatch(name="Nope"))
    with pytest.raises(NotFoundError):
        await service.delete_user(999)
    with pytest.raises(NotFoundError):
        await service.get_user_balance(999)
    with pytest.raises(NotFoundError):
        await service.get_user_email(999)


async def test_order_service_success_and_error_paths():
    orders = OrderRepoFake()
    users = UserRepoFake()
    products = ProductRepoFake()
    queue = FakeQueue()
    service = OrderService(orders, users, products, FakeCache(), queue)

    assert (await service.get_all_orders(10, 0))[0]["items"][0]["total"] == 20.0
    assert (await service.get_order_by_id(7))["id"] == 7

    order_create = OrderCreate(user_id=1, items=[OrderItemBase(product_id=1, quantity=2)])
    created = await service.create_order(order_create)
    assert created["order_id"] == 77
    assert created["total"] == 20.0
    assert products.product.quantity == 3
    assert users.user.balance == Decimal("80.00")
    assert orders.created_items[0]["order_id"] == 77

    deleted = await service.delete_order(7)
    assert deleted["id"] == 7
    assert queue.events[-1][1] == "order.deleted"

    async def empty_orders(limit=100, offset=0):
        return []

    orders.get_all = empty_orders
    with pytest.raises(NotFoundError):
        await service.get_all_orders()
    with pytest.raises(NotFoundError):
        await service.get_order_by_id(999)
    with pytest.raises(ValidationError):
        await service.create_order(OrderCreate(user_id=1, items=[OrderItemBase(product_id=1, quantity=0)]))
    with pytest.raises(NotFoundError):
        await service.delete_order(999)

    users.user = None
    with pytest.raises(NotFoundError):
        await service.create_order(order_create)


async def test_order_service_stock_balance_and_product_errors():
    orders = OrderRepoFake()
    users = UserRepoFake()
    products = ProductRepoFake()
    service = OrderService(orders, users, products, FakeCache(), FakeQueue())

    with pytest.raises(NotFoundError):
        await service.create_order(OrderCreate(user_id=1, items=[OrderItemBase(product_id=999, quantity=1)]))

    products.product.quantity = 1
    with pytest.raises(Exception):
        await service.create_order(OrderCreate(user_id=1, items=[OrderItemBase(product_id=1, quantity=2)]))

    products.product.quantity = 5
    users.user.balance = Decimal("1.00")
    with pytest.raises(BusinessLogicError):
        await service.create_order(OrderCreate(user_id=1, items=[OrderItemBase(product_id=1, quantity=2)]))
