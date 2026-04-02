from src.models.product import Product
from src.services.discount_service import DiscountStrategy


class ProductCalculator:
    @staticmethod
    def apply_discount(product: Product, discount: DiscountStrategy):
        return discount.apply(product.price)

    @staticmethod
    def calculate_total(product: Product):
        return product.price * product.quantity
