from src.models.product import Product
from src.models.user import User


class Order:
    def __init__(self, user: User, products: list[Product]):
        self.user = user
        self.products = products

    def calculate_total(self) -> float:
        total = 0
        for product in self.products:
            total += product.get_total_price()

        return total
