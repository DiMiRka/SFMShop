from src.utils.order_processor import load_orders_from_file, process_orders, analyze_orders
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
    logger.info(result)

    with open(output_file, "w", encoding="utf-8") as file:
        file.write(result)


if __name__ == "__main__":
    process_order_file("data/orders.txt", "data/processed_orders_report.txt")
