from dataclasses import dataclass
from abc import ABC, abstractmethod

from src.models.exceptions import NegativePriceError, InsufficientStockError, NegativeQuantityError
from src.models.mixins import LoggableMixin, SerializableMixin


class DiscountStrategy(ABC):
    @abstractmethod
    def apply(self, price: float):
        pass


class PercentDiscount(DiscountStrategy):
    def __init__(self, percent: float):
        self.percent = percent

    def apply(self, price: float):
        return price * (1 - self.percent / 100)


class FixedDiscount(DiscountStrategy):
    def __init__(self, amount: float):
        self.amount = amount

    def apply(self, price: float):
        return price - self.amount


@dataclass
class Product(LoggableMixin, SerializableMixin):
    name: str
    _price: float
    _quantity: int = 0

    def __post_init__(self):
        ProductValidator.validate(self)
        self.log(f"Создан: {self.name}")

    @property
    def price(self):
        return self._price

    @price.setter
    def price(self, price):
        if price < 0:
            self._price = 0
            raise NegativePriceError('Цена не может быть отрицательной')
        else:
            self._price = price

    @property
    def quantity(self):
        return self._quantity

    @quantity.setter
    def quantity(self, quantity):
        if quantity < 0:
            self._quantity = 0
            raise NegativeQuantityError('Количество не может быть отрицательным')
        else:
            self._quantity = quantity

    def __str__(self):
        return f"Товар: {self.name}, Цена: {self.price} руб., Количество: {self.quantity}"

    def __repr__(self):
        return f"Product('{self.name}', {self.price}, {self.quantity})"

    def __lt__(self, other):
        if isinstance(other, Product):
            return self.price < other.price
        else:
            return NotImplemented

    def __eq__(self, other):
        if isinstance(other, Product):
            return self.name == other.name and self.price == other.price
        else:
            return NotImplemented

    @classmethod
    def from_dict(cls, d):
        return cls(**d)

    def sell(self, amount: int):
        if self.quantity < amount:
            raise InsufficientStockError(f"Товара недостаточно. На складе: {self.quantity}, требуется: {amount}")
        self.quantity = self.quantity - amount


class ProductCalculator:
    @staticmethod
    def calculate_price(product: Product, discount: DiscountStrategy):
        return discount.apply(product.price)


class ProductValidator:
    @staticmethod
    def validate(product: Product):
        if product.price < 0:
            raise NegativePriceError('Цена не может быть отрицательной')
        if product.quantity < 0:
            raise NegativeQuantityError('Количество не может быть отрицательным')
