from decimal import Decimal
from types import SimpleNamespace

import pytest

from sfmshop.api.v1.auth import login, refresh_token, register
from sfmshop.api.v1.orders import cancel_order, delete_order, get_order, get_orders, pay_order, post_order
from sfmshop.api.v1.products import delete_product, get_product, get_products, post_product, put_product
from sfmshop.api.v1.users import delete_user, get_user, get_user_orders, get_users, put_user
from sfmshop.database.models import OrderItem as DbOrderItem
from sfmshop.database.models import Product as DbProduct
from sfmshop.database.models import User as DbUser
from sfmshop.repositories.order_repository import OrderRepository
from sfmshop.repositories.product_repository import ProductRepository
from sfmshop.repositories.user_repository import UserRepository
from sfmshop.schemas import OrderCreate, OrderItemBase, ProductCreate, ProductUpdate, UserCreate, UserUpdatePatch


pytestmark = pytest.mark.anyio


class ScalarResult:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class ExecuteResult:
    def __init__(self, values=None, scalar=None):
        self.values = values or []
        self._scalar = scalar

    def scalars(self):
        return ScalarResult(self.values)

    def scalar_one_or_none(self):
        return self._scalar

    def scalar(self):
        return self._scalar


class RepoDb:
    def __init__(self, result):
        self.result = result
        self.added = []
        self.deleted = []
        self.flushed = False

    async def execute(self, query):
        self.query = query
        return self.result

    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = 123
        self.added.append(obj)

    async def flush(self):
        self.flushed = True

    async def delete(self, obj):
        self.deleted.append(obj)


async def test_repositories_delegate_to_session_and_mutate_models():
    product = DbProduct(name="Keyboard", price=Decimal("100.00"), quantity=3)
    product.id = 5
    product_db = RepoDb(ExecuteResult([product], product))
    product_repo = ProductRepository(product_db)
    assert await product_repo.get_all() == [product]
    assert await product_repo.get_by_id(5) is product
    assert await product_repo.get_by_ids_for_update([5]) == [product]
    assert await product_repo.get_count_all() is product
    assert await product_repo.create({"name": "New", "price": Decimal("1.00"), "quantity": 1}) == 123
    await product_repo.update(product, {"name": "Changed"})
    assert product.name == "Changed"
    await product_repo.delete(product)
    assert product_db.deleted == [product]

    user = DbUser(name="U", email="u@test.com", age=18, balance=1, hashed_password="h")
    user.id = 6
    user_db = RepoDb(ExecuteResult([user], user))
    user_repo = UserRepository(user_db)
    assert await user_repo.get_all() == [user]
    assert await user_repo.get_by_id(6) is user
    assert await user_repo.get_by_id_for_update(6) is user
    assert await user_repo.get_by_email(user.email) is user
    created_user = await user_repo.create(
        {"name": "U", "email": "u2@test.com", "age": 18, "balance": 1, "hashed_password": "h"}
    )
    assert created_user.id == 123
    await user_repo.update(user, {"name": "Changed"})
    assert user.name == "Changed"
    await user_repo.delete(user)

    item = DbOrderItem(order_id=1, product_id=5, quantity=2, total=Decimal("20.00"))
    item.id = 8
    order_db = RepoDb(ExecuteResult([item], item))
    order_repo = OrderRepository(order_db)
    assert await order_repo.get_all() == [item]
    assert await order_repo.get_by_id(1) is item
    assert await order_repo.get_by_id_for_update(1) is item
    assert await order_repo.get_order_products(1) == [item]
    assert await order_repo.get_user_orders(1) == [item]
    assert await order_repo.get_order_ids_by_user(1) == [item]
    assert await order_repo.get_product_ids_by_user(1) == [item]
    assert await order_repo.create({"user_id": 1, "total": Decimal("20.00")}) == 123
    created_item = await order_repo.create_order_item(
        {"order_id": 1, "product_id": 5, "quantity": 2, "total": Decimal("20.00")}
    )
    assert created_item.id == 123
    await order_repo.delete(item)
    assert order_db.deleted == [item]

    empty_repo = OrderRepository(RepoDb(ExecuteResult([], None)))
    assert await empty_repo.get_order_ids_by_user(1) is None
    assert await empty_repo.get_product_ids_by_user(1) is None


async def test_api_route_functions_delegate_to_services():
    class Service:
        async def get_all_products(self, limit, offset): return ("products", limit, offset)
        async def get_product_by_id(self, product_id): return ("product", product_id)
        async def create_product(self, product): return product.name
        async def update_product(self, product_id, product): return (product_id, product.quantity)
        async def delete_product(self, product_id): return product_id
        async def get_users(self, limit, offset): return ("users", limit, offset)
        async def get_user_by_id(self, user_id): return ("user", user_id)
        async def update_user(self, user_id, user): return (user_id, user.name)
        async def delete_user(self, user_id): return user_id
        async def get_user_orders(self, user_id): return ("orders", user_id)
        async def get_all_orders(self, user_id, limit, offset): return ("orders", user_id, limit, offset)
        async def get_order_by_id(self, order_id, user_id): return ("order", order_id, user_id)
        async def create_order(self, user_id, order): return (user_id, len(order.items))
        async def pay_order(self, order_id, user_id): return ("pay", order_id, user_id)
        async def cancel_order(self, order_id, user_id): return ("cancel", order_id, user_id)
        async def delete_order(self, order_id): return order_id
        async def register_user(self, user): return user.email
        async def authorized_user(self, form_data): return form_data.username
        async def create_access_token_db(self, token): return token

    service = Service()
    cu = SimpleNamespace(id=1, is_admin=False)
    assert await get_products(service, None, 2, 3) == ("products", 2, 3)
    assert await get_product(service, 1) == ("product", 1)
    assert await post_product(cu, service, ProductCreate(name="A", price=Decimal("1.00"), quantity=1)) == "A"
    assert await put_product(cu, service, 1, ProductUpdate(quantity=2)) == (1, 2)
    assert await delete_product(cu, service, 1) == 1

    assert await get_users(cu, service, 2, 3) == ("users", 2, 3)
    assert await get_user(cu, service, 1) == ("user", 1)
    assert await put_user(cu, service, 1, UserUpdatePatch(name="A")) == (1, "A")
    assert await delete_user(cu, service, 1) == 1
    assert await get_user_orders(cu, service, 1) == ("orders", 1)

    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(queue=object())))
    order = OrderCreate(items=[OrderItemBase(product_id=1, quantity=1)])

    assert await get_orders(cu, service, 2, 3) == ("orders", 1, 2, 3)
    assert await get_order(cu, service, 1) == ("order", 1, 1)
    assert await post_order(request, cu, service, order) == (1, 1)
    assert await pay_order(cu, service, 1) == ("pay", 1, 1)
    assert await cancel_order(cu, service, 1) == ("cancel", 1, 1)


    admin = SimpleNamespace(id=9, is_admin=True)
    assert await get_orders(admin, service, 2, 3) == ("orders", None, 2, 3)
    assert await get_order(admin, service, 1) == ("order", 1, None)
    assert await cancel_order(admin, service, 1) == ("cancel", 1, None)
    assert await delete_order(admin, service, 1) == 1

    user = UserCreate(name="A", email="a@test.com", age=18, password="abc12345")
    assert await register(service, user) == "a@test.com"
    assert await login.__wrapped__(SimpleNamespace(), service, SimpleNamespace(username="u")) == "u"
    assert await refresh_token(service, "refresh") == "refresh"


def compiled_sql(query):
    from sqlalchemy.dialects import postgresql

    compiled = query.compile(dialect=postgresql.dialect())
    return str(compiled), compiled.params


async def test_product_search_applies_filters_and_escapes_wildcards():
    product = DbProduct(name="Mouse", price=Decimal("10.00"), quantity=3)
    db = RepoDb(ExecuteResult([product]))
    repo = ProductRepository(db)

    result = await repo.search(
        name_query="50%_off",
        min_price=Decimal("100.00"),
        max_price=Decimal("5000.00"),
        in_stock=True,
        limit=5,
    )

    assert result == [product]
    sql, params = compiled_sql(db.query)
    assert "products.name ILIKE" in sql and "ESCAPE" in sql
    assert "products.price >=" in sql and "products.price <=" in sql
    assert "products.quantity >" in sql
    assert r"%50\%\_off%" in params.values()
    assert Decimal("100.00") in params.values() and Decimal("5000.00") in params.values()
    assert params["param_1"] == 5


async def test_product_search_without_filters_caps_limit():
    db = RepoDb(ExecuteResult([]))
    repo = ProductRepository(db)

    assert await repo.search(limit=1000) == []

    sql, params = compiled_sql(db.query)
    assert "WHERE" not in sql
    assert params["param_1"] == 20


async def test_order_lists_can_be_sorted_newest_first():
    db = RepoDb(ExecuteResult([]))
    repo = OrderRepository(db)

    await repo.get_user_orders(1, 5, newest_first=True)
    assert "ORDER BY orders.id DESC" in compiled_sql(db.query)[0]

    await repo.get_all(5, newest_first=True)
    assert "ORDER BY orders.id DESC" in compiled_sql(db.query)[0]

    await repo.get_user_orders(1, 5)
    assert "ORDER BY orders.id DESC" not in compiled_sql(db.query)[0]
