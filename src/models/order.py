from datetime import datetime

from src.models.product import Product
from src.models.user import User
from src.models.exceptions import InvalidOrderError
from src.models.mixins import LoggableMixin, ValidatableMixin, SerializableMixin


class Order(LoggableMixin, ValidatableMixin, SerializableMixin):
    def __init__(self, order_id: int, user: User, products: list[Product]):
        self.validate()
        self.order_id = order_id
        self.user = user
        self.products = products
        self.created_at = datetime.now()
        self.log(f"Создан заказ: {order_id}")

    def __str__(self):
        return f"Заказ #{self.order_id} на сумму {self.calculate_total()} руб. (Пользователь: {self.user})"

    def __lt__(self, other):
        return self.created_at < other.created_at

    def __eq__(self, other):
        return self.order_id == other.order_id

    def validate(self):
        if self.user is None:
            raise InvalidOrderError("Пользователь не существует")
        if self.products is None:
            raise InvalidOrderError("Заказ невалиден: пустой список товаров")

    def calculate_total(self) -> float:
        return sum([product.get_total_price for product in self.products])

    def add_product(self, product: Product):
        if not isinstance(product, Product):
            raise InvalidOrderError("Такого продукта нет")
        else:
            self.products.append(product)
