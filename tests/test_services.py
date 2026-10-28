from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from pydantic import ValidationError as PydanticValidationError

from sfmshop.core.order_status import OrderStatus
from sfmshop.core.exceptions import PaymentUnavailableError, ForbiddenError, NotFoundError, UnauthorizedError, ValidationError
from sfmshop.database.models import Product as DbProduct, User as DbUser
from sfmshop.schemas import OrderCreate, OrderItemBase, ProductCreate, ProductUpdate, UserCreate, UserUpdatePatch
from sfmshop.core.security import get_password_hash, verify_password
from sfmshop.core.actor import Actor
from sfmshop.repositories.product_repository import SearchResult
from sfmshop.services.order_service import OrderService
from sfmshop.services.product_service import ProductService
from sfmshop.services.user_service import UserService
from sfmshop.clients.payment_client import PaymentResult, PaymentStatus


pytestmark = pytest.mark.anyio

ACTOR = Actor(1, "user")


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


class FakePayments:
    def __init__(self, balance=Decimal("100.00")):
        self.balances = {1: balance}
        self.payments = {500: {"order_id": 7, "user_id": 1, "amount": Decimal("20.00"), "status": "success"}}
        self.top_ups = {}
        self.refunds = []

    async def charge(self, order_id, user_id, amount):
        for payment_id, payment in self.payments.items():
            if payment["order_id"] == order_id and payment["status"] == "success":
                return PaymentResult(PaymentStatus.SUCCESS, payment_id)

        payment_id = 500 + len(self.payments)
        paid = self.balances.get(user_id, Decimal("0")) >= amount
        if paid:
            self.balances[user_id] -= amount
        self.payments[payment_id] = {"order_id": order_id, "user_id": user_id, "amount": amount,
                                     "status": "success" if paid else "failed"}
        if paid:
            return PaymentResult(PaymentStatus.SUCCESS, payment_id)
        return PaymentResult(PaymentStatus.FAILED, payment_id, "Недостаточно средств")

    async def refund(self, payment_id):
        payment = self.payments[payment_id]
        if payment["status"] == "success":
            self.balances[payment["user_id"]] += payment["amount"]
            payment["status"] = "refunded"
        self.refunds.append(payment_id)

    async def get_balance(self, user_id):
        return self.balances.get(user_id, Decimal("0"))

    async def top_up(self, user_id, amount, idempotency_key):
        if idempotency_key not in self.top_ups:
            self.top_ups[idempotency_key] = (user_id, amount)
            self.balances[user_id] = self.balances.get(user_id, Decimal("0")) + amount
        return self.balances[user_id]


class FakeQueue:
    def __init__(self):
        self.events = []
        self.message_ids = []

    async def publish_event(self, exchange, routing_key, message, message_id=None):
        self.events.append((exchange, routing_key, message))
        self.message_ids.append(message_id)
        return True


def db_product(product_id=1, name="Mouse", price=Decimal("10.00"), quantity=5):
    product = DbProduct(name=name, price=price, quantity=quantity)
    product.id = product_id
    product.created_at = datetime(2026, 1, 1)
    return product


def db_user(user_id=1, name="Dima", email="dima@test.com"):
    user = DbUser(name=name, email=email, age=30, hashed_password="hash", is_active=True, is_admin=False)
    user.id = user_id
    user.created_at = datetime(2026, 1, 1)
    return user


class ProductRepoFake:
    def __init__(self):
        self.db = FakeDb()
        self.product = db_product()
        self.products = [self.product]
        self.rating = (None, 0)
        self.updated = None
        self.deleted = None

    async def get_all(self, limit=100, offset=0):
        self.last_page = (limit, offset)
        return self.products

    async def get_count_all(self):
        return len(self.products)

    async def get_rating(self, product_id):
        return self.rating

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
        return db_user(2, data["name"], data["email"])

    async def update(self, user, data):
        self.updated = (user, data)
        for field, value in data.items():
            setattr(user, field, value)

    async def delete(self, user):
        self.deleted = user


class OrderRepoFake:
    def __init__(self):
        self.db = FakeDb()
        item = SimpleNamespace(id=10, product_id=1, quantity=2, total=Decimal("20.00"))
        self.order = SimpleNamespace(
            id=7,
            user_id=1,
            status=OrderStatus.PAID,
            payment_id=500,
            total=Decimal("20.00"),
            created_at=datetime(2026, 1, 1),
            items=[item],
        )
        self.orders = {7: self.order}
        self.created_items = []
        self.deleted = None

    async def get_all(self, limit=100, offset=0, newest_first=False):
        return [self.order]

    async def get_by_id(self, order_id):
        return self.orders.get(order_id)

    async def get_by_id_for_update(self, order_id):
        return await self.get_by_id(order_id)

    async def get_user_orders(self, user_id, limit=None, offset=0, newest_first=False):
        return [self.order] if user_id == self.order.user_id else []

    async def get_order_ids_by_user(self, user_id):
        return [self.order.id] if user_id == self.order.user_id else None

    async def get_product_ids_by_user(self, user_id):
        return [1] if user_id == self.order.user_id else None

    async def has_purchased(self, user_id, product_id):
        return user_id == self.order.user_id and any(item.product_id == product_id for item in self.order.items)

    async def get_order_products(self, order_id):
        return self.order.items if order_id == self.order.id else []

    async def create(self, data):
        self.created = data
        self.orders[77] = SimpleNamespace(
            **{"id": 77, "status": OrderStatus.PENDING, "payment_id": None, "created_at": datetime(2026, 1, 1), **data})
        return 77

    async def create_order_item(self, data):
        self.created_items.append(data)
        self.orders[data["order_id"]].items.append(SimpleNamespace(**data))
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
    assert await service.create_product(ProductCreate(name="New", price=Decimal("1.00"), quantity=1), actor=ACTOR) == {
        "id": 44,
        "message": "Товар добавлен",
    }
    assert await service.update_product(1, ProductUpdate(quantity=4), actor=ACTOR) == {
        "id": 1,
        "message": "Товар обновлен",
    }
    assert repo.updated[1] == {"quantity": 4}
    assert await service.delete_product(1, actor=ACTOR) == {"id": 1, "message": "Товар удален"}
    assert queue.events[-1][1] == "product.deleted"

    with pytest.raises(NotFoundError):
        await service.get_product_by_id(999)
    with pytest.raises(NotFoundError):
        await service.update_product(999, ProductUpdate(quantity=2), actor=ACTOR)
    with pytest.raises(NotFoundError):
        await service.delete_product(999, actor=ACTOR)


async def test_user_service_success_auth_and_not_found():
    users = UserRepoFake()
    orders = OrderRepoFake()
    queue = FakeQueue()
    service = UserService(users, orders, FakeCache(), queue)

    assert (await service.get_users(10, 0))[0]["email"] == "dima@test.com"
    assert (await service.get_user_by_id(1))["id"] == 1
    registered = await service.register_user(
        UserCreate(name="New", email="new@test.com", age=22, password="abc12345")
    )
    assert registered["email"] == "new@test.com"
    assert "balance" not in users.created and "balance" not in registered
    assert "is_admin" not in users.created
    assert registered["is_admin"] is False

    users.email_user = users.user
    with pytest.raises(ValidationError):
        await service.register_user(
            UserCreate(name="New", email="dima@test.com", age=22, password="abc12345")
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

    assert await service.update_user(1, UserUpdatePatch(name="Updated"), actor=ACTOR) == {
        "id": 1,
        "message": "Пользователь обновлен",
    }
    assert await service.delete_user(1, actor=ACTOR) == {"id": 1, "message": " Пользователь удален"}
    assert (await service.get_user_orders(1))[0]["id"] == 7

    with pytest.raises(NotFoundError):
        await service.get_user_by_id(999)
    with pytest.raises(NotFoundError):
        await service.update_user(999, UserUpdatePatch(name="Nope"), actor=ACTOR)
    with pytest.raises(NotFoundError):
        await service.delete_user(999, actor=ACTOR)


async def test_user_service_password_change_is_hashed_and_usable_for_login():
    users = UserRepoFake()
    service = UserService(users, OrderRepoFake(), FakeCache(), FakeQueue())
    users.email_user = users.user

    await service.update_user(1, UserUpdatePatch(password="newpass42", current_password="oldpass42"), actor=ACTOR)

    _, data = users.updated
    assert "password" not in data
    assert "current_password" not in data
    assert data["hashed_password"] != "newpass42"
    assert verify_password("newpass42", users.user.hashed_password)
    tokens = await service.authorized_user(SimpleNamespace(username="dima@test.com", password="newpass42"))
    assert tokens["access_token"]


async def test_user_service_inactive_user_cannot_login_or_refresh():
    users = UserRepoFake()
    service = UserService(users, OrderRepoFake(), FakeCache(), FakeQueue())
    users.email_user = users.user
    users.user.hashed_password = await get_password_hash("abc12345")
    form = SimpleNamespace(username="dima@test.com", password="abc12345")
    refresh_token = (await service.authorized_user(form))["refresh_token"]

    users.user.is_active = False

    with pytest.raises(ForbiddenError):
        await service.authorized_user(form)
    with pytest.raises(ForbiddenError):
        await service.create_access_token_db(refresh_token)
    # Без верного пароля статус аккаунта не раскрывается
    with pytest.raises(UnauthorizedError):
        await service.authorized_user(SimpleNamespace(username="dima@test.com", password="wrong"))


def test_user_update_rejects_weak_password():
    with pytest.raises(PydanticValidationError):
        UserUpdatePatch(password="onlyletters")
    with pytest.raises(PydanticValidationError):
        UserUpdatePatch(password="12345678")


async def test_order_service_success_and_error_paths():
    orders = OrderRepoFake()
    users = UserRepoFake()
    products = ProductRepoFake()
    queue = FakeQueue()
    payments = FakePayments()
    service = OrderService(orders, users, products, FakeCache(), queue, payments)

    assert (await service.get_all_orders(1, 10, 0))[0]["items"][0]["total"] == "20.00"
    assert (await service.get_order_by_id(7, 1))["id"] == 7

    order_create = OrderCreate(items=[OrderItemBase(product_id=1, quantity=2)])
    created = await service.create_order(1, order_create, actor=ACTOR)
    assert created == {
        "id": 77,
        "user_id": 1,
        "status": "paid",
        "total": "20.00",
        "created_at": "2026-01-01T00:00:00",
        "items": [{"product_id": 1, "quantity": 2, "total": "20.00"}],
    }
    assert products.product.quantity == 3
    assert payments.balances[1] == Decimal("80.00")
    assert orders.orders[77].payment_id == 501
    assert orders.created_items[0]["order_id"] == 77
    assert [event[1] for event in queue.events] == ["order.created", "order.paid"]

    deleted = await service.delete_order(7, actor=ACTOR)
    assert deleted["id"] == 7
    assert queue.events[-1][1] == "order.deleted"

    async def empty_orders(user_id, limit=None, offset=0, newest_first=False):
        return []

    orders.get_user_orders = empty_orders
    assert await service.get_all_orders(1) == []
    with pytest.raises(NotFoundError):
        await service.get_order_by_id(999, 1)
    with pytest.raises(ValidationError):
        await service.create_order(1, OrderCreate(items=[OrderItemBase(product_id=1, quantity=0)]), actor=ACTOR)
    with pytest.raises(NotFoundError):
        await service.delete_order(999, actor=ACTOR)

    users.user = None
    with pytest.raises(NotFoundError):
        await service.create_order(1, order_create, actor=ACTOR)


async def test_order_stays_pending_when_payment_service_is_unavailable():
    orders, products, queue = OrderRepoFake(), ProductRepoFake(), FakeQueue()
    service = OrderService(orders, UserRepoFake(), products, FakeCache(), queue, payments=None)

    created = await service.create_order(1, OrderCreate(items=[OrderItemBase(product_id=1, quantity=2)]), actor=ACTOR)

    assert created["status"] == "pending"
    assert products.product.quantity == 3
    assert [event[1] for event in queue.events] == ["order.created"]
    with pytest.raises(PaymentUnavailableError):
        await service.pay_order(77, 1, actor=ACTOR)
    with pytest.raises(PaymentUnavailableError):
        await service.delete_order(7, actor=ACTOR)
    assert orders.deleted is None


async def test_order_service_hides_foreign_orders():
    orders = OrderRepoFake()
    users = UserRepoFake()
    products = ProductRepoFake()
    cache = FakeCache()
    queue = FakeQueue()
    service = OrderService(orders, users, products, cache, queue)
    stranger_id = 2

    with pytest.raises(NotFoundError):
        await service.get_order_by_id(7, stranger_id)
    assert await service.get_all_orders(stranger_id) == []

    with pytest.raises(NotFoundError):
        await service.pay_order(7, stranger_id, actor=ACTOR)
    with pytest.raises(NotFoundError):
        await service.cancel_order(7, stranger_id, actor=ACTOR)
    assert orders.order.status == OrderStatus.PAID
    assert orders.deleted is None
    assert users.updated is None
    assert products.updated is None
    assert queue.events == []

    assert ("orders:2:100:0", 900) in cache.calls


async def test_order_service_admin_manages_any_order():
    orders = OrderRepoFake()
    users = UserRepoFake()
    products = ProductRepoFake()
    cache = FakeCache()
    payments = FakePayments()
    service = OrderService(orders, users, products, cache, FakeQueue(), payments)
    all_users = None

    orders.get_user_orders = None
    assert (await service.get_all_orders(all_users))[0]["id"] == 7
    assert ("orders:all:100:0", 900) in cache.calls
    assert (await service.get_order_by_id(7, all_users))["user_id"] == 1

    await service.delete_order(7, actor=ACTOR)
    assert orders.deleted is orders.order
    assert payments.refunds == [500]
    assert payments.balances[1] == Decimal("120.00")
    assert users.updated is None


async def test_order_service_stock_balance_and_product_errors():
    orders = OrderRepoFake()
    users = UserRepoFake()
    products = ProductRepoFake()
    payments = FakePayments(balance=Decimal("1.00"))
    service = OrderService(orders, users, products, FakeCache(), FakeQueue(), payments)

    with pytest.raises(NotFoundError):
        await service.create_order(1, OrderCreate(items=[OrderItemBase(product_id=999, quantity=1)]), actor=ACTOR)

    products.product.quantity = 1
    with pytest.raises(Exception):
        await service.create_order(1, OrderCreate(items=[OrderItemBase(product_id=1, quantity=2)]), actor=ACTOR)

    products.product.quantity = 5
    created = await service.create_order(1, OrderCreate(items=[OrderItemBase(product_id=1, quantity=2)]), actor=ACTOR)
    assert created["status"] == "failed"
    assert payments.balances[1] == Decimal("1.00")
    assert products.product.quantity == 3


async def test_paid_order_refund_with_kopecks_and_locked_stock_return():
    orders = OrderRepoFake()
    orders.order.total = Decimal("20.25")
    users = UserRepoFake()
    payments = FakePayments(balance=Decimal("100.50"))
    payments.payments[500]["amount"] = Decimal("20.25")
    products = ProductRepoFake()

    async def unlocked_read(ids):
        raise AssertionError("товары при возврате на склад должны блокироваться")

    products.get_by_ids = unlocked_read
    products.get_by_ids_for_update = lambda ids: async_return([p for p in products.products if p.id in ids])
    service = OrderService(orders, users, products, FakeCache(), FakeQueue(), payments)

    await service.delete_order(7, actor=ACTOR)

    assert payments.refunds == [500]
    assert payments.balances[1] == Decimal("120.75")
    assert products.product.quantity == 7


async def async_return(value):
    return value


async def test_product_search_passes_filters_and_serializes_out_of_stock_product():
    class SearchRepo(ProductRepoFake):
        async def search(self, **filters):
            self.filters = filters
            return SearchResult([db_product(2, "Cable", Decimal("150.50"), 0)], 1, False)

    repo = SearchRepo()
    service = ProductService(repo, FakeCache(), FakeQueue())

    result = await service.search_products("cab", Decimal("100"), None, False, 3)

    assert repo.filters == {
        "name_query": "cab", "min_price": Decimal("100"), "max_price": None, "in_stock": False, "limit": 3,
    }
    assert result == [{
        "id": 2, "name": "Cable", "description": None, "price": "150.50", "quantity": 0,
        "created_at": "2026-01-01T00:00:00",
    }]


async def test_catalog_search_returns_page_with_fuzzy_flag():
    class SearchRepo(ProductRepoFake):
        async def search(self, **filters):
            self.filters = filters
            return SearchResult([db_product(2, "Мышь беспроводная", Decimal("990.00"), 4)], 7, True)

    repo = SearchRepo()

    result = await ProductService(repo, FakeCache(), FakeQueue()).search_catalog("мыш беспроводня", 1, 3)

    assert repo.filters == {"name_query": "мыш беспроводня", "limit": 1, "offset": 3}
    assert result["total"] == 7 and result["fuzzy"] is True
    assert (result["limit"], result["offset"]) == (1, 3)
    assert result["products"][0]["name"] == "Мышь беспроводная"
