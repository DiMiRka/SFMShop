from src.utils.order_processor import load_orders_from_file, process_orders, analyze_orders
from src.models import Product, User, Order, CardPayment, PayPalPayment
from src.models.exceptions import *

from loguru import logger


def process_order_file(input_file, output_file):
    data = load_orders_from_file(input_file)
    orders = process_orders(data)
    analyze = analyze_orders(orders)
    stats_str = ", ".join(f"{key}: {value}" for key, value in analyze["by_status"].items())

    result = f"""Обработано заказов: {analyze["total_orders"]}
Общая сумма: {analyze["total_sum"]} руб.
По статусам: {stats_str}
Уникальных пользователя: {len(analyze["unique_users"])}
"""

    with open(output_file, "w", encoding="utf-8") as file:
        file.write(result)


if __name__ == "__main__":
    process_order_file("data/orders.txt", "data/processed_orders_report.txt")

    user_1 = User("Иван Иванов", "ivan@test.com")
    product_1 = Product("Ноутбук", 50000, 1)
    product_2 = Product("Мышь", 1500, 2)
    order = Order(1, user_1, [product_1, product_2])

    print("------------------------------")
    print("ООП Урок 1 КЛАССЫ")
    print(order.calculate_total())
    print(user_1.get_info())
    print("------------------------------")

    print("ООП Урок 2 ПРИНЦИПЫ ООП")
    card_payment = CardPayment(3000, "1234 5678 9012 3456")
    paypal_payment = PayPalPayment(2500, "user@paypal.com")

    payments = [card_payment, paypal_payment]
    for payment in payments:
        print(payment.process_payment())
    print("------------------------------")

    print("ООП Урок 3 МАГИЧЕСКИЕ МЕТОДЫ")
    products = [
        Product("Ноутбук", 50000, 10),
        Product("Мышь", 1500, 20),
        Product("Клавиатура", 3000, 15)
    ]
    products.sort()
    for product in products:
        print(product)

    order_2 = Order(2, user_1, products)
    print(order_2)
    print("------------------------------")

    print("ООП Урок 4 ОСНОВЫ ИСКЛЮЧЕНИЙ")
    try:
        product_fail = Product("Монитор", -500, 1)
    except NegativePriceError as e:
        print(e)
    try:
        user_fail = User("Dima", "dimirkabk.ru")
    except ValueError as e:
        print(e)
    print("------------------------------")

    print("ООП Урок 5 СОЗДАНИЕ СОБСТВЕННЫХ ИСКЛЮЧЕНИЙ")
    try:
        product = Product("Клавиатура", -2000, 1)
    except NegativePriceError as e:
        logger.error(f"Ошибка валидации: {e}")
    except ValidationError as e:
        logger.error(f"Общая ошибка валидации: {e}")

    try:
        product = Product("Наушники", 500, 7)
        product.sell(10)
    except InsufficientStockError as e:
        logger.error(f"Ошибка бизнес-логики: {e}")
    except BusinessLogicError as e:
        logger.error(f"Общая ошибка бизнес-логики: {e}")

    try:
        user = User("Dima", "dimirka@bk.ru")
        order = Order(1, user, [])
    except InvalidOrderError as e:
        logger.error(f"Ошибка бизнес-логики: {e}")
    except BusinessLogicError as e:
        logger.error(f"Общая ошибка бизнес-логики: {e}")

    print("------------------------------")

    print("ООП ПРАКТИЧЕСКОЕ ЗАДАНИЕ")

    def process_order_system():
        user_new = User("Дима", "dimirka@bk.ru")

        product1 = Product("Ноутбук", 50000, 2)
        product2 = Product("Мышь", 1500, 3)

        order_new = Order(5, user_new, [product1, product2])

        total = order_new.calculate_total()
        print("Общая стоимость заказа:", total)

        payments_new = [
            CardPayment(1000, "1234 5678 9012 3456"),
            PayPalPayment(2000, "test@paypal.com")
        ]

        for pay in payments_new:
            print(pay.process_payment())

        sorted_products = sorted([product1, product2])
        for prod in sorted_products:
            print(prod)

        try:
            product.set_price(-1000)
        except ValidationError as ex:
            print("Ошибка валидации:", ex)

    process_order_system()
