import asyncio
import aiohttp
import time


async def process_order(order_id: int):
    await asyncio.sleep(0.1)

    return f"Заказ {order_id} обработан"


async def process_orders_async(order_ids: list):
    tasks = [process_order(order_id) for order_id in order_ids]
    results = await asyncio.gather(*tasks)
    return results


async def main():
    order_ids = list(range(1, 101))

    start = time.time()
    results = await process_orders_async(order_ids)
    end = time.time()
    print(f"Параллельные запросы выполнены за {end - start:.4f} секунд")

if __name__ == "__main__":
    asyncio.run(main())
