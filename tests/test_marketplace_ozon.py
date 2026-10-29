import json
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
from prometheus_client import REGISTRY

from sfmshop.clients.marketplaces import (Marketplace, MarketplaceOrder, MarketplaceOrderItem, OzonClient, PriceUpdate,
                                          StockUpdate, UpdateResult, create_marketplace_clients)
from sfmshop.clients.marketplaces import http as marketplace_http
from sfmshop.clients.marketplaces.http import MarketplaceHttp
from sfmshop.core.config import AppSettings
from sfmshop.core.exceptions import MarketplaceRequestError, MarketplaceUnavailableError, ServiceUnavailableError


pytestmark = pytest.mark.anyio


class Transport:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        if isinstance(response, httpx.Response):
            return response
        status, body = response
        return httpx.Response(status, json=body)

    def bodies(self):
        return [json.loads(request.content) for request in self.requests]


@pytest.fixture
def delays(monkeypatch):
    recorded = []

    async def fake_sleep(delay):
        recorded.append(delay)

    monkeypatch.setattr(marketplace_http.asyncio, "sleep", fake_sleep)
    return recorded


def make_client(transport, max_retries=2):
    http_client = httpx.AsyncClient(base_url="https://ozon", transport=httpx.MockTransport(transport))
    return OzonClient(MarketplaceHttp("ozon", http_client, max_retries=max_retries), warehouse_id=777)


def requests_metric(result):
    return REGISTRY.get_sample_value("sfmshop_marketplace_requests_total",
                                     {"marketplace": "ozon", "result": result}) or 0


def stock_result(offer_id, updated=True, errors=()):
    return {"offer_id": offer_id, "product_id": 1, "warehouse_id": 777, "updated": updated, "errors": list(errors)}


def ok_stocks(offer_ids):
    return 200, {"result": [stock_result(offer_id) for offer_id in offer_ids]}


async def test_update_stocks_splits_into_batches_of_100_with_warehouse(delays):
    stocks = [StockUpdate(f"SKU-{i}", i) for i in range(250)]
    transport = Transport(
        ok_stocks(f"SKU-{i}" for i in range(100)),
        ok_stocks(f"SKU-{i}" for i in range(100, 200)),
        ok_stocks(f"SKU-{i}" for i in range(200, 250)),
    )

    results = await make_client(transport).update_stocks(stocks)

    bodies = transport.bodies()
    assert [len(body["stocks"]) for body in bodies] == [100, 100, 50]
    assert bodies[0]["stocks"][3] == {"offer_id": "SKU-3", "stock": 3, "warehouse_id": 777}
    assert all(request.url.path == "/v2/products/stocks" for request in transport.requests)
    assert len(results) == 250
    assert all(result.updated for result in results)


async def test_update_stocks_throttles_to_80_requests_per_minute(delays):
    transport = Transport(ok_stocks(["A"]), ok_stocks(["B"]), ok_stocks(["C"]))
    client = make_client(transport)

    for offer_id in "ABC":
        await client.update_stocks([StockUpdate(offer_id, 1)])

    assert len(delays) == 2
    assert delays == pytest.approx([0.75, 1.5], abs=0.05)


async def test_item_errors_inside_http_200_are_returned_per_offer(delays):
    transport = Transport((200, {"result": [
        stock_result("OK-1"),
        stock_result("BAD-1", updated=False, errors=[{"code": "TOO_MANY_REQUESTS", "message": "wait 30 seconds"}]),
    ]}))

    results = await make_client(transport).update_stocks([StockUpdate("OK-1", 5), StockUpdate("BAD-1", 3)])

    assert results == [
        UpdateResult("OK-1", updated=True),
        UpdateResult("BAD-1", updated=False, error="TOO_MANY_REQUESTS: wait 30 seconds"),
    ]


async def test_retries_429_using_retry_after_header(delays):
    transport = Transport(
        httpx.Response(429, json={"code": 8, "message": "rate limit"}, headers={"Retry-After": "7"}),
        ok_stocks(["A"]),
    )
    before = requests_metric("ok")

    results = await make_client(transport).update_stocks([StockUpdate("A", 1)])

    assert results == [UpdateResult("A", updated=True)]
    assert len(transport.requests) == 2
    assert 7 in delays
    assert requests_metric("ok") == before + 1


async def test_retries_5xx_with_exponential_backoff_then_gives_up(delays):
    transport = Transport((500, {}), (502, {}), (503, {}))
    before = requests_metric("unavailable")

    with pytest.raises(MarketplaceUnavailableError) as exc_info:
        await make_client(transport, max_retries=2).update_prices([PriceUpdate("A", Decimal("10"))])

    assert isinstance(exc_info.value, ServiceUnavailableError)
    assert len(transport.requests) == 3
    assert delays == [1.0, 2.0]
    assert requests_metric("unavailable") == before + 1


async def test_timeout_is_retried(delays):
    transport = Transport(httpx.ReadTimeout("slow"), (200, {"result": [{"offer_id": "A", "updated": True}]}))

    results = await make_client(transport).update_prices([PriceUpdate("A", Decimal("10"))])

    assert results == [UpdateResult("A", updated=True)]
    assert len(transport.requests) == 2


async def test_client_error_is_not_retried(delays):
    transport = Transport((400, {"code": 3, "message": "invalid offer_id"}))
    before = requests_metric("error")

    with pytest.raises(MarketplaceRequestError, match="HTTP 400: invalid offer_id"):
        await make_client(transport).update_prices([PriceUpdate("A", Decimal("10"))])

    assert len(transport.requests) == 1
    assert delays == []
    assert requests_metric("error") == before + 1


async def test_update_prices_sends_price_as_string_in_batches_of_1000(delays):
    prices = [PriceUpdate(f"SKU-{i}", Decimal("1448.50")) for i in range(1001)]
    transport = Transport((200, {"result": []}), (200, {"result": []}))

    await make_client(transport).update_prices(prices)

    bodies = transport.bodies()
    assert transport.requests[0].url.path == "/v1/product/import/prices"
    assert [len(body["prices"]) for body in bodies] == [1000, 1]
    assert bodies[0]["prices"][0] == {"offer_id": "SKU-0", "price": "1448.50", "currency_code": "RUB"}


def posting(number, offer_id="SKU-1", quantity=1, amount="12990.00"):
    return {
        "posting_number": number,
        "status": "awaiting_packaging",
        "in_process_at": "2026-05-14T08:00:00.000Z",
        "products": [{"offer_id": offer_id, "quantity": quantity, "price": {"amount": amount, "currency": "RUB"}}],
    }


async def test_fetch_orders_follows_cursor_and_parses_money_as_decimal(delays):
    transport = Transport(
        (200, {"postings": [posting("1-1", quantity=2, amount="100.50")], "has_next": True, "cursor": "next-page"}),
        (200, {"postings": [posting("2-1")], "has_next": False, "cursor": ""}),
    )
    since = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)

    orders = await make_client(transport).fetch_orders(since)

    first, second = transport.bodies()
    assert transport.requests[0].url.path == "/v4/posting/fbs/list"
    assert first["filter"]["since"] == "2026-10-01T12:00:00Z"
    assert first["limit"] == 100
    assert first["cursor"] == ""
    assert second["cursor"] == "next-page"
    assert orders[0] == MarketplaceOrder(
        external_id="1-1",
        status="awaiting_packaging",
        created_at=datetime(2026, 5, 14, 8, 0, tzinfo=UTC),
        items=[MarketplaceOrderItem("SKU-1", 2, Decimal("100.50"))],
    )
    assert orders[0].total == Decimal("201.00")
    assert [order.external_id for order in orders] == ["1-1", "2-1"]


def test_module_disabled_without_keys():
    assert create_marketplace_clients(AppSettings(_env_file=None)) == {}
    assert create_marketplace_clients(AppSettings(_env_file=None, ozon_client_id="1", ozon_api_key="key")) == {}


async def test_ozon_client_built_from_settings():
    clients = create_marketplace_clients(AppSettings(
        _env_file=None, ozon_client_id="123", ozon_api_key="secret", ozon_warehouse_id=777,
    ))

    client = clients[Marketplace.OZON]
    assert isinstance(client, OzonClient)
    assert client.warehouse_id == 777
    assert str(client.http.http_client.base_url) == "https://api-seller.ozon.ru"
    assert client.http.http_client.headers["Client-Id"] == "123"
    assert client.http.http_client.headers["Api-Key"] == "secret"
    await client.close()
