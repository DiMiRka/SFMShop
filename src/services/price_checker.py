import asyncio
import random


async def check_supplier(name: str, product_id: int, delay: float, price: int):
    await asyncio.sleep(delay)
    return {"supplier": name, "product_id": product_id, "price": price}


async def check_supplier_timeout(name: str):
    await asyncio.sleep(10)
    raise TimeoutError(f"Поставщик {name} не отвечает")


async def find_best_price(product_id: int) -> dict:
    results = await asyncio.gather(
        check_supplier("Альфа", product_id, 1.0, 1500),
        check_supplier("Бета", product_id, 0.5, 1200),
        check_supplier_timeout("Гамма"),
        check_supplier("Дельта", product_id, 1.5, 1350),
        return_exceptions=True
    )

    valid_results = [r for r in results if not isinstance(r, Exception)]

    if not valid_results:
        return {"error": "Ни один поставщик не ответил"}

    best = min(valid_results, key=lambda x: x["price"])

    return best


async def order_producer(queue: asyncio.Queue, num_orders: int, num_workers: int):
    for i in range(num_orders):
        order = {
            "id": i + 1,
            "total": random.randint(500, 10000),
            "items": random.randint(1, 5)
        }
        await queue.put(order)
        print(f"Новый заказ #{order['id']} — {order['total']} руб.")
        await asyncio.sleep(0.3)

    for _ in range(num_workers):
        await queue.put(None)


async def order_worker(name: str, queue: asyncio.Queue):
    processed = 0
    while True:
        order = await queue.get()

        if order is None:
            print(f"Worker {name}: завершение (обработано {processed} заказов)")
            break

        processing_time = order["items"] * 0.3
        print(f"Worker {name}: обработка заказа #{order['id']}...")
        await asyncio.sleep(processing_time)
        print(f"Worker {name}: заказ #{order['id']} готов")

        processed += 1
        queue.task_done()


async def main():
    queue = asyncio.Queue(maxsize=5)
    num_workers = 3
    num_orders = 10

    await asyncio.gather(
        order_producer(queue, num_orders, num_workers),
        order_worker("A", queue),
        order_worker("B", queue),
        order_worker("C", queue),
    )

    print("Все заказы обработаны")

    try:
        result = await asyncio.wait_for(find_best_price(42), timeout=3.0)
        print(f"Лучшая цена: {result}")
    except asyncio.TimeoutError:
        print("Превышено время ожидания")


asyncio.run(main())
