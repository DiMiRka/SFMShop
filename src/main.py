from src.models.order_factory import OrderFactory
from src.models.delivery_strategy import StandardDelivery
from src.models.payment import CardPayment
from src.models import Product, User


def process_advanced_order_system():

    order = OrderFactory.create_order(1, [], User)

    delivery = StandardDelivery()
    delivery_cost = delivery.calculate_cost(5.0)

    payment = CardPayment(1000, "1234 5678 9123 4567")
    payment.process_payment()

    order_json = order.to_dict()

    product = Product("Ноутбук", 1000, 10)

    payment.log("Платеж обработан")

    print(len(order))
    print("Ноутбук" in order)

    return {
        "order": order_json,
        "delivery_cost": delivery_cost,
        "product": product.to_dict()
    }
