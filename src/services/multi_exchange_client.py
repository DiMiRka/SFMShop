import asyncio
import httpx
from typing import Optional, List
from loguru import logger

from src.core.config import app_settings


class MultiExchangeClient:

    def __init__(self,
                 api_urls: List[str] | None = None,
                 timeout: float | None = None,
                 max_retries: int | None = None,
                 backoff_base: float | None = None):
        self.api_urls = api_urls or app_settings.exchange_api_urls
        self.timeout = timeout if timeout is not None else app_settings.exchange_timeout
        self.max_retries = max_retries if max_retries is not None else app_settings.exchange_max_retries
        self.backoff_base = backoff_base if backoff_base is not None else app_settings.exchange_backoff_base
        self.client = httpx.AsyncClient(timeout=self.timeout)

    async def get_exchange_rate(self, base: str, target: str) -> Optional[float]:

        for api_url in self.api_urls:

            logger.info(f"exchange_api_attempt url={api_url}")

            url = f"{api_url}/{base}"

            for attempt in range(self.max_retries):
                try:
                    response = await self.client.get(url)
                    response.raise_for_status()

                    data = response.json()

                    rate = data.get("rates", {}).get(target)

                    if rate is None:
                        logger.warning(f"currency_not_found target={target} url={api_url}")
                        return None

                    logger.info(f"exchange_rate_received url={api_url} rate={rate}")

                    return rate

                except (httpx.ReadTimeout, httpx.ConnectTimeout) as e:
                    if attempt < self.max_retries - 1:
                        delay = self.backoff_base ** attempt
                        logger.warning(f"exchange_api_error url={api_url} retry_in={delay}")

                        await asyncio.sleep(delay)
                    else:
                        logger.warning(f"exchange_api_unavailable url={api_url}")
                        return None

                except httpx.HTTPStatusError as e:
                    logger.warning(f"exchange_http_error error={e}")
                    return None

        logger.warning("all_exchange_apis_unavailable")
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
    client = MultiExchangeClient()

    price = 1000

    converted_price = await client.convert_price(price, "USD", "RUB")
    if converted_price:
        print(f"{price} USD = {converted_price} RUB")
    else:
        print("exchange_rate_unavailable")

if __name__ == "__main__":
    asyncio.run(main())
