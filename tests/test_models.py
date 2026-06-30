import pytest

from src.models.order import Order, OrderCalculator
from src.models.product import Product


def test_create_product(sample_product):
    assert sample_product.name == "Monitor"
    assert sample_product.price == 15000
    assert sample_product.quantity == 3


def test_product_get_total_price(sample_product):
    assert sample_product.get_total_price() == 45000


def test_create_user(sample_user):
    assert sample_user.name == "Dima"
    assert sample_user.email == "dima@test.com"
    assert sample_user.balance == 666000


def test_create_order(sample_order, sample_user, sample_product):
    assert sample_order.user == sample_user
    assert sample_order.products == [sample_product]


def test_order_calculate_total(sample_user, sample_product):
    product2 = Product("Headset", 6000, 2)
    order = Order(sample_user, [sample_product, product2])

    assert order.calculate_total() == 57000


@pytest.mark.parametrize(
    "discount_percent,expected",
    [
        (0, 45000),
        (5, 42750),
        (10, 40500),
        (15, 38250),
        (100, 0),
    ],
)
def test_calculate_discount_all_cases(sample_order, discount_percent, expected):
    assert OrderCalculator.calculate_discount(sample_order, discount_percent) == expected


@pytest.mark.parametrize(
    "weight,distance,expected",
    [
        (1, 10, 160),
        (5, 50, 400),
        (10, 100, 700),
    ]
)
def test_calculate_delivery(weight, distance, expected):
    assert OrderCalculator.calculate_delivery(weight, distance) == expected
