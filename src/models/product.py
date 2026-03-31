from dataclasses import dataclass

from src.models.exceptions import NegativePriceError, InsufficientStockError, NegativeQuantityError
from src.models.mixins import LoggableMixin, ValidatableMixin, SerializableMixin


@dataclass
class Product(LoggableMixin, ValidatableMixin, SerializableMixin):
    name: str
    _price: float
    _quantity: int = 0

    def __post_init__(self):
        self.validate()
        self.log(f"Создан: {self.name}")

    def validate(self):
        if self._price < 0:
            raise NegativePriceError('Цена не может быть отрицательной')
        if self._quantity < 0:
            raise NegativeQuantityError('Количество не может быть отрицательным')

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

    @staticmethod
    def calculate_discount(price, discount):
        return price * (1 + discount)

    def sell(self, amount: int):
        if self.quantity < amount:
            raise InsufficientStockError(f"Товара недостаточно. На складе: {self.quantity}, требуется: {amount}")
        self.quantity = self.quantity - amount

    def get_total_price(self) -> float:
        return self.price * self.quantity

