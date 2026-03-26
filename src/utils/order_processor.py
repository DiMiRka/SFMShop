from loguru import logger


def load_orders_from_file(filename: str = "src/data/orders.txt") -> list | None:
    try:
        with open(filename, "r", encoding="utf-8") as file:
            result = []
            for line in file.readlines():
                line = line.strip().split(':')
                try:
                    line[1] = float(line[1])
                    result.append(line)
                except ValueError:
                    logger.error(f"Ошибка в строке {line}\nВторым аргументом должно быть число")
        logger.info(result)
        return result
    except FileNotFoundError:
        logger.error(f"Файл {filename} не найден")


def calculate_order_total(price: float, discount_rate: float) -> float:
    return round(price * (1 + discount_rate), 2)


def get_discount_by_total(total: float) -> float:
    if total > 1000:
        return 0.15
    elif total > 500:
        return 0.10
    elif total > 0:
        return 0.05
    else:
        return 0.0


def process_orders(orders_data: list) -> list[dict]:
    result = []
    for order in orders_data:
        discount = get_discount_by_total(float(order[1]))
        total = calculate_order_total(float(order[1]), discount)
        result.append({"order_id": order[0],
                       "total": total,
                       "status": order[2],
                       "user": order[3]})
    logger.info(result)
    return result


def analyze_orders(processed_orders):
    stats = {
        "total_orders": 0,
        "total_sum": 0,
        "by_status": {},
        "unique_users": set()
    }

    for order in processed_orders:
        stats["total_orders"] += 1
        stats["total_sum"] += order["total"]
        if not order["status"] in stats["by_status"].keys():
            stats["by_status"][order["status"]] = 1
        else:
            stats["by_status"][order["status"]] += 1
        stats["unique_users"].add(order["user"])

    stats["unique_users"] = list(stats["unique_users"])
    logger.info(stats)
    return stats
