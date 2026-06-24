import pytest
from src.models.order import Order
from src.models.user import User
from src.models.product import Product


def test_create_product():
    product = Product("Монитор", 15000, 3)
    assert product.name == "Монитор"
    assert product.price == 15000
    assert product.quantity == 3


@pytest.fixture()
def sample_product():
    return Product("Монитор", 15000, 3)


def test_product_get_total_price(sample_product):
    assert sample_product.get_total_price() == 45000


def test_create_user():
    user = User(1, "Дима", "dimir@test.com", 31, 666000)
    assert user.name == "Дима"
    assert user.email == "dimir@test.com"
    assert user.balance == 666000


@pytest.fixture()
def sample_user():
    return User(1, "Дима", "dimir@test.com", 31, 666000)


def test_create_order(sample_user, sample_product):
    order = Order(sample_user, [sample_product])
    assert order.user == sample_user
    assert len(order.products) == 1


def test_order_calculate_total(sample_user, sample_product):
    product1 = sample_product
    product2 = Product("Гарнитура", 6000, 2)
    order = Order(sample_user, [product1, product2])
    total = order.calculate_total()
    assert total == 57000
