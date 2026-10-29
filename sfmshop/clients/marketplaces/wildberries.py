from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sfmshop.clients.marketplaces.base import (Marketplace, MarketplaceOrder, MarketplaceOrderItem, PriceUpdate,
                                               StockUpdate, UpdateResult)
from sfmshop.clients.marketplaces.http import MarketplaceHttp, Throttle, batched


PRICES_PATH = "/api/v2/upload/task"
STOCKS_PATH = "/api/v3/stocks/{warehouse_id}"
ORDERS_PATH = "/api/v3/orders"
ORDER_STATUSES_PATH = "/api/v3/orders/status"

PRICES_BATCH = 1000
STOCKS_BATCH = 1000
ORDERS_PAGE = 1000
ORDER_STATUSES_BATCH = 1000
ORDERS_MAX_PERIOD = timedelta(days=30)
PRICES_INTERVAL = 0.6
MARKETPLACE_INTERVAL = 0.2
ALREADY_SET = "already set"


class WildberriesClient:
    marketplace = Marketplace.WILDBERRIES

    def __init__(self, http: MarketplaceHttp, prices_url: str, marketplace_url: str, warehouse_id: int):
        self.http = http
        self.prices_url = prices_url.rstrip("/")
        self.marketplace_url = marketplace_url.rstrip("/")
        self.warehouse_id = warehouse_id
        self.prices_throttle = Throttle(PRICES_INTERVAL)
        self.marketplace_throttle = Throttle(MARKETPLACE_INTERVAL)

    async def update_stocks(self, stocks: list[StockUpdate]) -> list[UpdateResult]:
        sendable = [stock for stock in stocks if stock.size_id is not None]
        results = [UpdateResult(stock.offer_id, updated=False, error="Не указан chrtId размера")
                   for stock in stocks if stock.size_id is None]
        url = self.marketplace_url + STOCKS_PATH.format(warehouse_id=self.warehouse_id)

        for batch in batched(sendable, STOCKS_BATCH):
            payload = {"stocks": [{"chrtId": stock.size_id, "amount": stock.quantity} for stock in batch]}
            await self.http.request("PUT", url, json=payload, throttle=self.marketplace_throttle)
            results += [UpdateResult(stock.offer_id, updated=True) for stock in batch]
        return results

    async def update_prices(self, prices: list[PriceUpdate]) -> list[UpdateResult]:
        sendable = [price for price in prices if price.product_id is not None]
        results = [UpdateResult(price.offer_id, updated=False, error="Не указан nmID товара")
                   for price in prices if price.product_id is None]

        for batch in batched(sendable, PRICES_BATCH):
            payload = {"data": [{"nmID": price.product_id, "price": whole_rubles(price.price)} for price in batch]}
            response = await self.http.request("POST", self.prices_url + PRICES_PATH, json=payload,
                                               throttle=self.prices_throttle, allowed_statuses=frozenset({400}))
            body = response.json()
            error = body.get("errorText") if body.get("error") else None
            if error and ALREADY_SET in error:
                error = None
            results += [UpdateResult(price.offer_id, updated=error is None, error=error) for price in batch]
        return results

    async def fetch_orders(self, since: datetime) -> list[MarketplaceOrder]:
        now = datetime.now(UTC)
        params = {
            "limit": ORDERS_PAGE,
            "next": 0,
            "dateFrom": int(max(since, now - ORDERS_MAX_PERIOD).timestamp()),
            "dateTo": int(now.timestamp()),
        }
        raw_orders: list[dict[str, Any]] = []
        while True:
            body = (await self.http.request("GET", self.marketplace_url + ORDERS_PATH, params=params,
                                            throttle=self.marketplace_throttle)).json()
            page = body.get("orders") or []
            raw_orders += page
            if len(page) < ORDERS_PAGE:
                break
            params["next"] = body["next"]

        statuses = await self.fetch_statuses([order["id"] for order in raw_orders])
        return [to_order(order, statuses.get(order["id"], "unknown")) for order in raw_orders]

    async def fetch_statuses(self, order_ids: list[int]) -> dict[int, str]:
        statuses: dict[int, str] = {}
        for batch in batched(order_ids, ORDER_STATUSES_BATCH):
            body = (await self.http.request("POST", self.marketplace_url + ORDER_STATUSES_PATH,
                                            json={"orders": list(batch)}, throttle=self.marketplace_throttle)).json()
            statuses |= {item["id"]: item["wbStatus"] for item in body.get("orders", [])}
        return statuses

    async def close(self) -> None:
        await self.http.close()


def whole_rubles(price: Decimal) -> int:
    return int(price.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def to_order(order: dict[str, Any], status: str) -> MarketplaceOrder:
    return MarketplaceOrder(
        external_id=str(order["id"]),
        status=status,
        created_at=datetime.fromisoformat(order["createdAt"]),
        items=[MarketplaceOrderItem(
            offer_id=order["article"],
            quantity=1,
            price=Decimal(order["convertedPrice"]) / 100,
        )],
    )
