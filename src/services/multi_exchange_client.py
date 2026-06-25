import asyncio
import httpx
from typing import Optional, List
from loguru import logger


class MultiExchangeClient:

    def __init__(self,
                 api_urls: List[str],
                 timeout: int = 5,
                 max_retries: int = 3):
        self.api_urls = api_urls
        self.timeout = timeout
        self.max_retries = max_retries
        self.client = httpx.AsyncClient(timeout=self.timeout)

    async def get_exchange_rate(self, base: str, target: str) -> Optional[float]:

        for api_url in self.api_urls:

            logger.info(f"Попытка получить курс из {api_url}")

            url = f"{api_url}/{base}"

            for attempt in range(self.max_retries):
                try:
                    response = await self.client.get(url)
                    response.raise_for_status()

                    data = response.json()

                    rate = data.get("rates", {}).get(target)

                    if rate is None:
                        logger.warning(f"Валюта {target} не найдена в {api_url}")
                        return None

                    logger.info(f"Курс получен из {api_url}: {rate}")

                    return rate

                except (httpx.ReadTimeout, httpx.ConnectTimeout) as e:
                    if attempt < self.max_retries - 1:
                        delay = 2 ** attempt
                        logger.warning(f"Ошибка {api_url}, повтор через {delay} сек...")

                        await asyncio.sleep(delay)
                    else:
                        logger.warning(f"API {api_url} недоступен, пробуем следующий")
                        return None

                except httpx.HTTPStatusError as e:
                    logger.warning(f"Ошибка запроса: {e}")
                    return None

        logger.warning("Все API не доступны")
        return None

    async def convert_price(
            self,
            price: float,
            from_currency: str,
            to_currency: str
    ) -> Optional[float]:

        if from_currency == to_currency:
            return price

        rate = await self.get_exchange_rate(from_currency, to_currency)
        if rate is None:
            return None

        return price * rate

    async def close(self):
        await self.client.aclose()


async def main():
    client = MultiExchangeClient([
        "https://api.exchangerate-api.com/v4/latest",
        "https://api.currencyapi.com/v3/latest",
        "https://api.fixer.io/latest"
    ])

    price = 1000

    converted_price = await client.convert_price(price, "USD", "RUB")
    if converted_price:
        print(f"{price} USD = {converted_price} RUB")
    else:
        print("Не удалось получить курс валют")

if __name__ == "__main__":
    asyncio.run(main())
