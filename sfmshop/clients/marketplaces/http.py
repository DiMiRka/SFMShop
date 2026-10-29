import asyncio
from typing import Any

import httpx

from sfmshop.core.exceptions import MarketplaceRequestError, MarketplaceUnavailableError
from sfmshop.core.metrics import MARKETPLACE_REQUESTS
from sfmshop.services.log_service import log_service


RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})


class Throttle:
    def __init__(self, interval: float):
        self.interval = interval
        self.next_at = 0.0
        self.lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self.lock:
            now = asyncio.get_running_loop().time()
            if self.next_at > now:
                await asyncio.sleep(self.next_at - now)
            self.next_at = max(now, self.next_at) + self.interval


class MarketplaceHttp:
    def __init__(
            self,
            marketplace: str,
            http_client: httpx.AsyncClient,
            retry_after_header: str = "Retry-After",
            max_retries: int = 3,
            base_delay: float = 1.0,
            max_delay: float = 30.0):
        self.marketplace = marketplace
        self.http_client = http_client
        self.retry_after_header = retry_after_header
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay

    async def request(
            self,
            method: str,
            url: str,
            json: Any = None,
            params: dict[str, Any] | None = None,
            throttle: Throttle | None = None,
            allowed_statuses: frozenset[int] = frozenset()) -> httpx.Response:
        reason = ""

        for attempt in range(self.max_retries + 1):
            if throttle is not None:
                await throttle.wait()

            retry_after = None
            try:
                response = await self.http_client.request(method, url, json=json, params=params)
            except httpx.TransportError as exc:
                reason = type(exc).__name__
            else:
                if response.is_success or response.status_code in allowed_statuses:
                    MARKETPLACE_REQUESTS.labels(self.marketplace, "ok").inc()
                    return response
                if response.status_code not in RETRYABLE_STATUSES:
                    MARKETPLACE_REQUESTS.labels(self.marketplace, "error").inc()
                    detail = error_detail(response)
                    log_service.warning("marketplace_request_failed", marketplace=self.marketplace, url=url,
                                        status_code=response.status_code, detail=detail)
                    raise MarketplaceRequestError(f"{self.marketplace}: HTTP {response.status_code}: {detail}")
                reason = f"http_{response.status_code}"
                retry_after = parse_seconds(response.headers.get(self.retry_after_header))

            if attempt < self.max_retries:
                delay = retry_after if retry_after is not None else self.base_delay * 2 ** attempt
                log_service.warning("marketplace_retry", marketplace=self.marketplace, url=url,
                                    attempt=attempt + 1, reason=reason)
                await asyncio.sleep(min(delay, self.max_delay))

        MARKETPLACE_REQUESTS.labels(self.marketplace, "unavailable").inc()
        log_service.warning("marketplace_unavailable", marketplace=self.marketplace, url=url, reason=reason)
        raise MarketplaceUnavailableError(f"{self.marketplace} временно недоступен: {reason}")

    async def close(self) -> None:
        await self.http_client.aclose()


def parse_seconds(value: str | None) -> float | None:
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


def error_detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text[:200]
    if isinstance(body, dict):
        return str(body.get("message") or body.get("errorText") or body.get("detail") or body)[:200]
    return str(body)[:200]
