from datetime import datetime
from dataclasses import dataclass
from typing import List

from src.models.product import Product, ProductCalculator
from src.models.user import User
from src.models.exceptions import InvalidOrderError
from src.models.mixins import LoggableMixin, SerializableMixin
from src.models.metaclasses import ModelMeta


@dataclass
class Order(LoggableMixin, SerializableMixin, metaclass=ModelMeta):
    order_id: int
    user: User
    products: List[Product]
    created_at: datetime = datetime.now()

    def __post_init__(self):
        OrderValidator.validate(self)
        self.log(f"Создан заказ: {self.order_id}")

    def __str__(self):
        return f"Заказ #{self.order_id} на сумму {OrderCalculator.calculate_total(self)} руб. (Пользователь: {self.user})"

    def __lt__(self, other):
        return self.created_at < other.created_at

    def __eq__(self, other):
        return self.order_id == other.order_id

    def add_product(self, product: Product):
        if not isinstance(product, Product):
            raise InvalidOrderError("Такого продукта нет")
        else:
            self.products.append(product)


class OrderCalculator:
    @staticmethod
    def calculate_total(order: Order) -> float:
        return sum([ProductCalculator.calculate_total(product) for product in order.products])


class OrderValidator:
    @staticmethod
    def validate(order: Order):
        if not order.user:
            raise InvalidOrderError("Пользователь не существует")
        if not order.products:
            raise InvalidOrderError("Заказ невалиден: пустой список товаров")
