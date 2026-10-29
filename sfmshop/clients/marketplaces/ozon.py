from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sfmshop.clients.marketplaces.base import (Marketplace, MarketplaceOrder, MarketplaceOrderItem, PriceUpdate,
                                               StockUpdate, UpdateResult)
from sfmshop.clients.marketplaces.http import MarketplaceHttp, Throttle, batched


STOCKS_PATH = "/v2/products/stocks"
PRICES_PATH = "/v1/product/import/prices"
POSTINGS_PATH = "/v4/posting/fbs/list"

STOCKS_BATCH = 100
PRICES_BATCH = 1000
POSTINGS_PAGE = 100
STOCKS_REQUESTS_PER_MINUTE = 80


class OzonClient:
    marketplace = Marketplace.OZON

    def __init__(self, http: MarketplaceHttp, warehouse_id: int):
        self.http = http
        self.warehouse_id = warehouse_id
        self.stocks_throttle = Throttle(60 / STOCKS_REQUESTS_PER_MINUTE)

    async def update_stocks(self, stocks: list[StockUpdate]) -> list[UpdateResult]:
        results: list[UpdateResult] = []
        for batch in batched(stocks, STOCKS_BATCH):
            payload = {"stocks": [
                {"offer_id": stock.offer_id, "stock": stock.quantity, "warehouse_id": self.warehouse_id}
                for stock in batch
            ]}
            response = await self.http.request("POST", STOCKS_PATH, json=payload, throttle=self.stocks_throttle)
            results += item_results(response.json())
        return results

    async def update_prices(self, prices: list[PriceUpdate]) -> list[UpdateResult]:
        results: list[UpdateResult] = []
        for batch in batched(prices, PRICES_BATCH):
            payload = {"prices": [
                {"offer_id": price.offer_id, "price": str(price.price), "currency_code": "RUB"}
                for price in batch
            ]}
            response = await self.http.request("POST", PRICES_PATH, json=payload)
            results += item_results(response.json())
        return results

    async def fetch_orders(self, since: datetime) -> list[MarketplaceOrder]:
        orders: list[MarketplaceOrder] = []
        period = {"since": iso(since), "to": iso(datetime.now(UTC))}
        cursor = ""
        while True:
            payload = {"filter": period, "limit": POSTINGS_PAGE, "cursor": cursor, "sort_dir": "ASC"}
            body = (await self.http.request("POST", POSTINGS_PATH, json=payload)).json()
            orders += [to_order(posting) for posting in body.get("postings", [])]
            cursor = body.get("cursor", "")
            if not body.get("has_next") or not cursor:
                return orders

    async def close(self) -> None:
        await self.http.close()


def item_results(body: dict[str, Any]) -> list[UpdateResult]:
    return [
        UpdateResult(
            offer_id=item["offer_id"],
            updated=bool(item.get("updated")),
            error="; ".join(f"{error.get('code')}: {error.get('message')}" for error in item.get("errors") or [])
                  or None,
        )
        for item in body.get("result", [])
    ]


def to_order(posting: dict[str, Any]) -> MarketplaceOrder:
    return MarketplaceOrder(
        external_id=posting["posting_number"],
        status=posting["status"],
        created_at=datetime.fromisoformat(posting["in_process_at"]),
        items=[
            MarketplaceOrderItem(
                offer_id=product["offer_id"],
                quantity=product["quantity"],
                price=Decimal(product["price"]["amount"]),
            )
            for product in posting["products"]
        ],
    )


def iso(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
