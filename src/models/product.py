from dataclasses import dataclass
from abc import ABC, abstractmethod

from src.models.exceptions import InsufficientStockError
from src.models.mixins import LoggableMixin, SerializableMixin
from src.models.metaclasses import ModelMeta
from src.models.descriptors import PositiveNumber, CachedProperty


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
class Product(metaclass=ModelMeta, LoggableMixin, SerializableMixin):
    name: str
    price: float = PositiveNumber("_price")
    quantity: int = PositiveNumber("_quantity")

    def __post_init__(self):
        self.log(f"Создан: {self.name}")

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
    @CachedProperty
    def calculate_price(product: Product, discount: DiscountStrategy):
        return discount.apply(product.price)

    @staticmethod
    @CachedProperty
    def calculate_total(product: Product):
        return product.price * product.quantity
