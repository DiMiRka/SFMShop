import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest

from sfmshop.clients.marketplaces import (Marketplace, PriceUpdate, StockUpdate, UpdateResult, WildberriesClient,
                                          create_marketplace_clients)
from sfmshop.clients.marketplaces import http as marketplace_http
from sfmshop.clients.marketplaces.http import MarketplaceHttp
from sfmshop.core.config import AppSettings
from sfmshop.core.exceptions import MarketplaceRequestError
from tests.test_marketplace_ozon import Transport


pytestmark = pytest.mark.anyio


@pytest.fixture
def delays(monkeypatch):
    recorded = []

    async def fake_sleep(delay):
        recorded.append(delay)

    monkeypatch.setattr(marketplace_http.asyncio, "sleep", fake_sleep)
    return recorded


def make_client(transport, max_retries=2):
    http_client = httpx.AsyncClient(transport=httpx.MockTransport(transport))
    http = MarketplaceHttp("wildberries", http_client, retry_after_header="X-Ratelimit-Retry", max_retries=max_retries)
    return WildberriesClient(http, prices_url="https://prices", marketplace_url="https://marketplace",
                             warehouse_id=555)


TASK_OK = (200, {"data": {"id": 1, "alreadyExists": False}, "error": False, "errorText": ""})


async def test_update_stocks_puts_size_ids_to_warehouse_in_batches(delays):
    stocks = [StockUpdate(f"SKU-{i}", i, size_id=1000 + i) for i in range(1001)]
    transport = Transport(httpx.Response(204), httpx.Response(204))

    results = await make_client(transport).update_stocks(stocks)

    bodies = transport.bodies()
    assert transport.requests[0].method == "PUT"
    assert str(transport.requests[0].url) == "https://marketplace/api/v3/stocks/555"
    assert [len(body["stocks"]) for body in bodies] == [1000, 1]
    assert bodies[0]["stocks"][2] == {"chrtId": 1002, "amount": 2}
    assert len(results) == 1001
    assert all(result.updated for result in results)


async def test_stock_without_size_id_is_not_sent(delays):
    transport = Transport(httpx.Response(204))

    results = await make_client(transport).update_stocks([StockUpdate("NO-SIZE", 3), StockUpdate("OK", 1, size_id=7)])

    assert transport.bodies() == [{"stocks": [{"chrtId": 7, "amount": 1}]}]
    assert results == [
        UpdateResult("NO-SIZE", updated=False, error="Не указан chrtId размера"),
        UpdateResult("OK", updated=True),
    ]


async def test_update_prices_sends_whole_rubles_by_nm_id(delays):
    transport = Transport(TASK_OK)

    results = await make_client(transport).update_prices([
        PriceUpdate("A", Decimal("999.50"), product_id=11),
        PriceUpdate("B", Decimal("1000.49"), product_id=12),
        PriceUpdate("NO-NM", Decimal("10")),
    ])

    assert str(transport.requests[0].url) == "https://prices/api/v2/upload/task"
    assert transport.bodies() == [{"data": [{"nmID": 11, "price": 1000}, {"nmID": 12, "price": 1000}]}]
    assert results == [
        UpdateResult("NO-NM", updated=False, error="Не указан nmID товара"),
        UpdateResult("A", updated=True),
        UpdateResult("B", updated=True),
    ]


async def test_prices_already_set_400_is_not_an_error(delays):
    transport = Transport((400, {"data": None, "error": True,
                                 "errorText": "The specified prices and discounts are already set"}))

    results = await make_client(transport).update_prices([PriceUpdate("A", Decimal("100"), product_id=1)])

    assert results == [UpdateResult("A", updated=True)]
    assert len(transport.requests) == 1


async def test_rejected_price_batch_marks_its_items_and_next_batch_still_goes(delays):
    prices = [PriceUpdate(f"SKU-{i}", Decimal("100"), product_id=i) for i in range(1001)]
    transport = Transport((400, {"data": None, "error": True, "errorText": "Invalid price value"}), TASK_OK)

    results = await make_client(transport).update_prices(prices)

    assert len(transport.requests) == 2
    assert results[0] == UpdateResult("SKU-0", updated=False, error="Invalid price value")
    assert sum(not result.updated for result in results) == 1000
    assert results[-1] == UpdateResult("SKU-1000", updated=True)


async def test_stocks_400_is_still_a_request_error(delays):
    transport = Transport((400, {"code": "IncorrectRequestBody", "message": "Incorrect required body"}))

    with pytest.raises(MarketplaceRequestError, match="Incorrect required body"):
        await make_client(transport).update_stocks([StockUpdate("A", 1, size_id=1)])


async def test_retries_429_using_x_ratelimit_retry(delays):
    transport = Transport(
        httpx.Response(429, json={"title": "too many requests"}, headers={"X-Ratelimit-Retry": "2"}),
        TASK_OK,
    )

    results = await make_client(transport).update_prices([PriceUpdate("A", Decimal("100"), product_id=1)])

    assert results == [UpdateResult("A", updated=True)]
    assert 2 in delays


def wb_order(order_id, article="SKU-1", converted_price=101450):
    return {"id": order_id, "article": article, "createdAt": "2026-10-28T07:56:29Z",
            "nmId": 1, "chrtId": 2, "price": converted_price, "convertedPrice": converted_price}


async def test_fetch_orders_pages_by_next_and_loads_statuses(delays):
    first_page = [wb_order(i) for i in range(1000)]
    transport = Transport(
        (200, {"next": 999, "orders": first_page}),
        (200, {"next": 1000, "orders": [wb_order(1000, article="SKU-2")]}),
        (200, {"orders": [{"id": i, "supplierStatus": "new", "wbStatus": "waiting"} for i in range(1000)]}),
        (200, {"orders": []}),
    )
    since = datetime.now(UTC) - timedelta(days=90)

    orders = await make_client(transport).fetch_orders(since)

    first, second, *status_requests = transport.requests
    assert first.url.path == "/api/v3/orders"
    assert first.url.params["next"] == "0"
    assert second.url.params["next"] == "999"
    assert int(first.url.params["dateFrom"]) >= int((datetime.now(UTC) - timedelta(days=30, minutes=1)).timestamp())
    assert [request.url.path for request in status_requests] == ["/api/v3/orders/status"] * 2
    assert [len(json.loads(request.content)["orders"]) for request in status_requests] == [1000, 1]

    assert len(orders) == 1001
    assert orders[0].external_id == "0"
    assert orders[0].status == "waiting"
    assert orders[0].created_at == datetime(2026, 10, 28, 7, 56, 29, tzinfo=UTC)
    assert orders[0].items[0].offer_id == "SKU-1"
    assert orders[0].items[0].quantity == 1
    assert orders[0].total == Decimal("1014.50")
    assert orders[-1].status == "unknown"


def test_wildberries_disabled_without_token_or_warehouse():
    assert Marketplace.WILDBERRIES not in create_marketplace_clients(AppSettings(_env_file=None, wb_api_token="t"))
    assert Marketplace.WILDBERRIES not in create_marketplace_clients(AppSettings(_env_file=None, wb_warehouse_id=1))


async def test_wildberries_client_built_from_settings():
    clients = create_marketplace_clients(AppSettings(_env_file=None, wb_api_token="token", wb_warehouse_id=555))

    client = clients[Marketplace.WILDBERRIES]
    assert isinstance(client, WildberriesClient)
    assert client.http.http_client.headers["Authorization"] == "token"
    assert client.http.retry_after_header == "X-Ratelimit-Retry"
    assert client.prices_url == "https://discounts-prices-api.wildberries.ru"
    assert client.marketplace_url == "https://marketplace-api.wildberries.ru"
    await client.close()
