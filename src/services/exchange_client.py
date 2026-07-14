import asyncio
from typing import Optional

import httpx
from loguru import logger

from src.core.config import app_settings


class ExchangeRateClient:

    def __init__(self,
                 base_url: str | None = None,
                 timeout: float | None = None,
                 max_retries: int | None = None,
                 backoff_base: float | None = None):
        self.base_url = base_url or app_settings.exchange_api_url
        self.timeout = timeout if timeout is not None else app_settings.exchange_timeout
        self.max_retries = max_retries if max_retries is not None else app_settings.exchange_max_retries
        self.backoff_base = backoff_base if backoff_base is not None else app_settings.exchange_backoff_base
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
                    logger.warning(f"currency_not_found target={target}")
                    return None

                return rate

            except httpx.ReadTimeout:
                if attempt < self.max_retries - 1:
                    delay = self.backoff_base ** attempt
                    logger.warning(f"exchange_timeout retry_in={delay}")
                    await asyncio.sleep(delay)
                else:
                    logger.warning("exchange_timeout_retries_exceeded")
                    return None

            except httpx.ConnectError:
                if attempt < self.max_retries - 1:
                    delay = self.backoff_base ** attempt
                    logger.warning(f"exchange_connect_error retry_in={delay}")
                    await asyncio.sleep(delay)
                else:
                    logger.warning("exchange_connect_retries_exceeded")
                    return None

            except httpx.HTTPStatusError as e:
                logger.warning(f"exchange_http_error error={e}")
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
        print("exchange_rate_unavailable")

if __name__ == "__main__":
    asyncio.run(main())
