import asyncio
import aiohttp
import time


async def fetch_url_async(url: str):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    return None
    except Exception as e:
        print(f"Ошибка при запросе к {url}: {e}")
        return None


async def fetch_multiple_urls_async(urls: list):
    tasks = [fetch_url_async(url) for url in urls]
    results = await asyncio.gather(*tasks)
    return results


async def main():
    urls = [
        "https://api.example.com/data1",
        "https://api.example.com/data2",
        "https://api.example.com/data3"
    ]

    start = time.time()
    results = await fetch_multiple_urls_async(urls)
    end = time.time()
    print(f"Параллельные запросы выполнены за {end - start} секунд")
    print(f"Результат: {results}")

if __name__ == "__main__":
    asyncio.run(main())
