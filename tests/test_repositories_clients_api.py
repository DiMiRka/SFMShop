from decimal import Decimal
from types import SimpleNamespace

import httpx
import pytest

from src.api.v1.auth import login, refresh_token, register
from src.api.v1.orders import delete_order, get_order, get_orders, post_order
from src.api.v1.products import delete_product, get_product, get_products, post_product, put_product
from src.api.v1.users import delete_user, get_user, get_user_orders, get_users, put_user
from src.clients.payment_client import PaymentClient
from src.database.models import OrderItem as DbOrderItem
from src.database.models import Product as DbProduct
from src.database.models import User as DbUser
from src.repositories.order_repository import OrderRepository
from src.repositories.product_repository import ProductRepository
from src.repositories.user_repository import UserRepository
from src.schemas import OrderCreate, OrderItemBase, ProductCreate, ProductUpdate, UserCreate, UserUpdatePatch
from src.services.exchange_client import ExchangeRateClient
from src.services.multi_exchange_client import MultiExchangeClient


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
    assert await product_repo.get_by_ids([5]) == [product]
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
    assert await user_repo.get_balance(6) is user
    assert await user_repo.get_email(6) is user

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


class HttpResponse:
    def __init__(self, data=None, error=None):
        self._data = data or {}
        self.error = error

    def raise_for_status(self):
        if self.error:
            raise self.error

    def json(self):
        return self._data


class HttpClientFake:
    def __init__(self, responses):
        self.responses = list(responses)
        self.closed = False

    async def get(self, url):
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    async def aclose(self):
        self.closed = True


async def test_exchange_clients_convert_and_handle_errors(monkeypatch):
    async def no_sleep(delay):
        return None

    monkeypatch.setattr("src.services.exchange_client.asyncio.sleep", no_sleep)
    monkeypatch.setattr("src.services.multi_exchange_client.asyncio.sleep", no_sleep)

    client = ExchangeRateClient(max_retries=2)
    client.client = HttpClientFake([HttpResponse({"rates": {"RUB": 90}}), HttpResponse({"rates": {"RUB": 90}})])
    assert await client.get_exchange_rate("USD", "RUB") == 90
    assert await client.convert_price(2, "USD", "RUB") == 180
    assert await client.convert_price(2, "USD", "USD") == 2
    await client.close()
    assert client.client.closed

    client.client = HttpClientFake([HttpResponse({"rates": {}})])
    assert await client.get_exchange_rate("USD", "EUR") is None
    client.client = HttpClientFake([httpx.ReadTimeout("timeout"), HttpResponse({"rates": {"EUR": 2}})])
    assert await client.get_exchange_rate("USD", "EUR") == 2
    client.client = HttpClientFake([httpx.ConnectError("boom"), httpx.ConnectError("boom")])
    assert await client.get_exchange_rate("USD", "EUR") is None
    request = httpx.Request("GET", "https://test")
    response = httpx.Response(500, request=request)
    client.client = HttpClientFake([HttpResponse(error=httpx.HTTPStatusError("bad", request=request, response=response))])
    assert await client.get_exchange_rate("USD", "EUR") is None
    client.client = HttpClientFake([HttpResponse({"rates": {}})])
    assert await client.convert_price(2, "USD", "EUR") is None

    multi = MultiExchangeClient(["https://one", "https://two"], max_retries=2)
    multi.client = HttpClientFake([HttpResponse({"rates": {"EUR": 3}}), HttpResponse({"rates": {"EUR": 3}})])
    assert await multi.get_exchange_rate("USD", "EUR") == 3
    assert await multi.convert_price(2, "USD", "EUR") == 6
    assert await multi.convert_price(2, "USD", "USD") == 2
    await multi.close()
    assert multi.client.closed

    multi.client = HttpClientFake([httpx.ConnectTimeout("no"), httpx.ConnectTimeout("no")])
    assert await multi.get_exchange_rate("USD", "EUR") is None
    multi.client = HttpClientFake([HttpResponse({"rates": {}})])
    assert await multi.convert_price(2, "USD", "EUR") is None


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
        async def get_all_orders(self, limit, offset): return ("orders", limit, offset)
        async def get_order_by_id(self, order_id): return ("order", order_id)
        async def create_order(self, order): return order.user_id
        async def delete_order(self, order_id): return order_id
        async def register_user(self, user): return user.email
        async def authorized_user(self, form_data): return form_data.username
        async def create_access_token_db(self, token): return token

    service = Service()
    cu = object()
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
    order = OrderCreate(user_id=1, items=[OrderItemBase(product_id=1, quantity=1)])
    assert await get_orders(cu, service, 2, 3) == ("orders", 2, 3)
    assert await get_order(cu, service, 1) == ("order", 1)
    assert await post_order(request, cu, service, order) == 1
    assert await delete_order(cu, service, 1) == 1

    user = UserCreate(name="A", email="a@test.com", age=18, balance=1, password="abc12345")
    assert await register(service, user) == "a@test.com"
    assert await login.__wrapped__(SimpleNamespace(), service, SimpleNamespace(username="u")) == "u"
    assert await refresh_token(service, "refresh") == "refresh"


async def test_payment_client_success_and_request_error(monkeypatch):
    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json, timeout):
            return HttpResponse({"paid": True})

    monkeypatch.setattr(httpx, "AsyncClient", Client)
    assert await PaymentClient("https://pay").process_payment(1, 10.0) == {"paid": True}

    class ErrorClient(Client):
        async def post(self, url, json, timeout):
            raise httpx.RequestError("network")

    monkeypatch.setattr(httpx, "AsyncClient", ErrorClient)
    assert await PaymentClient("https://pay").process_payment(1, 10.0) is None

