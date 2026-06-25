import pytest

from src.models.order import Order
from src.models.product import Product
from src.models.user import User


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def sample_product():
    return Product("Monitor", 15000, 3)


@pytest.fixture
def sample_user():
    return User(1, "Dima", "dima@test.com", 31, 666000)


@pytest.fixture
def sample_order(sample_user, sample_product):
    return Order(sample_user, [sample_product])
