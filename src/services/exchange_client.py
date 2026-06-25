import httpx
import asyncio
from typing import Optional
from loguru import logger


class ExchangeRateClient:

    def __init__(self,
                 base_url: str = "https://api.exchangerate-api.com/v4/latest",
                 timeout: int = 5,
                 max_retries: int = 3):
        self.base_url = base_url
        self.timeout = timeout
        self.max_retries = max_retries
        self.client = httpx.AsyncClient(timeout=self.timeout)

    async def get_exchange_rate(self, base: str, target: str) -> Optional[float]:

        url = f"{self.base_url}/{base}"

        for attempt in range(self.max_retries):
            try:
                response = await self.client.get(url)
                response.raise_for_status()

                data = response.json()

                rate = data.get("rates", {}).get(target)

                if rate is None:
                    logger.warning(f"Валюта {target} не найдена")
                    return None

                return rate

            except httpx.ReadTimeout:
                if attempt < self.max_retries - 1:
                    delay = 2 ** attempt
                    logger.warning(f"Таймаут, повтор через {delay} сек...")
                    await asyncio.sleep(delay)
                else:
                    logger.warning("Превышено время ожидания после всех попыток")
                    return None

            except httpx.ConnectError:
                if attempt < self.max_retries - 1:
                    delay = 2 ** attempt
                    logger.warning(f"Ошибка подключения, повтор через {delay} сек...")
                    await asyncio.sleep(delay)
                else:
                    logger.warning("Ошибка подключения после всех попыток")
                    return None

            except httpx.HTTPStatusError as e:
                logger.warning(f"Ошибка запроса: {e}")
                return None

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
    client = ExchangeRateClient()

    price = 1000

    converted_price = await client.convert_price(price, "USD", "RUB")
    if converted_price:
        print(f"{price} USD = {converted_price} RUB")
    else:
        print("Не удалось получить курс валют")

if __name__ == "__main__":
    asyncio.run(main())
