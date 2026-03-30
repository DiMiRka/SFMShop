from datetime import timedelta

from src.utils.order_processor import load_orders_from_file, process_orders, analyze_orders
from src.models import Product, User, Order, CardPayment, PayPalPayment
from src.models.exceptions import *
from src.database.connection import *
from src.database.queries import *

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
    print("СУБД урок 3")
    with connect_to_db() as conn:
        add_product(conn, "Телевизор", 55000, 1)
        print(get_all_products(conn))
        update_product_price(conn, 1, 4000)
        print("----------------------------------")

        create_user(conn, "Dima", "dimirka@bk.ru")
        get_user_by_id(conn, 1)
        create_order(conn, 1, 5)
        get_user_orders(conn, 1)

        print("----------------------------------")
        print("СУБД Практическое задание")

        create_user(conn, "Alex","alex@bk.ru")
        get_all_products(conn)
        get_order_statistics(conn)
        get_top_products(conn)
        get_user_by_id(conn, 1)
        get_user_order_history(conn, 1)
