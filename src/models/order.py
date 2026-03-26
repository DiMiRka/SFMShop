from src.models.product import Product
from src.models.user import User


class Order:
    def __init__(self, order_id: int, user: User, products: list[Product]):
        self.order_id = order_id
        self.user = user
        self.products = products

    def calculate_total(self) -> float:
        total = 0
        for product in self.products:
            total += product.get_total_price()

        return total

    def __str__(self):
        return f"Заказ #{self.order_id} на сумму {self.calculate_total()} руб. (Пользователь: {self.user})"