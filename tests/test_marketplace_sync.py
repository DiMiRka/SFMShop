from decimal import Decimal

import pytest
from prometheus_client import REGISTRY

from sfmshop.clients.marketplaces import PriceUpdate, StockUpdate, UpdateResult
from sfmshop.core.exceptions import MarketplaceUnavailableError
from sfmshop.repositories.marketplace_listing_repository import ListingState
from sfmshop.services.marketplace_sync_service import MarketplaceSyncService, PushResult


pytestmark = pytest.mark.anyio


def metric(name, **labels):
    return REGISTRY.get_sample_value(name, labels) or 0


class Session:
    commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def commit(self):
        Session.commits += 1


class Store:
    def __init__(self, states):
        self.states = states
        self.saved = []
        self.errors = {}

    def repository(self, session):
        return FakeListingRepository(self)


class FakeListingRepository:
    def __init__(self, store):
        self.store = store

    async def get_states(self, marketplace):
        return self.store.states.get(marketplace, [])

    async def save_results(self, rows):
        self.store.saved += rows

    async def set_error(self, marketplace, error):
        self.store.errors[marketplace] = error


class FakeMarketplace:
    def __init__(self, fail=None, rejected=(), missing=()):
        self.fail = fail
        self.rejected = set(rejected)
        self.missing = set(missing)
        self.stock_calls = []
        self.price_calls = []

    def _results(self, items):
        if self.fail:
            raise self.fail
        return [
            UpdateResult(item.offer_id, updated=False, error="TOO_MANY_REQUESTS: wait")
            if item.offer_id in self.rejected else UpdateResult(item.offer_id, updated=True)
            for item in items if item.offer_id not in self.missing
        ]

    async def update_stocks(self, stocks):
        self.stock_calls.append(stocks)
        return self._results(stocks)

    async def update_prices(self, prices):
        self.price_calls.append(prices)
        return self._results(prices)


def state(listing_id, offer_id, quantity=5, price="100.00", synced_quantity=None, synced_price=None,
          external_product_id=None, external_size_id=None):
    return ListingState(
        id=listing_id, offer_id=offer_id, external_product_id=external_product_id, external_size_id=external_size_id,
        synced_quantity=synced_quantity, synced_price=Decimal(synced_price) if synced_price else None,
        quantity=quantity, price=Decimal(price),
    )


def make_service(store, clients):
    return MarketplaceSyncService(Session, clients, store.repository)


async def test_pushes_only_changed_values_and_saves_them():
    store = Store({"ozon": [
        state(1, "A", quantity=7, price="100.00", synced_quantity=5, synced_price="100.00"),
        state(2, "B", quantity=3, price="50.00", synced_quantity=3, synced_price="50.00"),
    ]})
    ozon = FakeMarketplace()

    results = await make_service(store, {"ozon": ozon}).push_stocks_and_prices()

    assert results == {"ozon": PushResult(stocks_updated=1, prices_updated=0, failed=0)}
    assert ozon.stock_calls == [[StockUpdate("A", 7)]]
    assert ozon.price_calls == []
    [row] = store.saved
    assert row["id"] == 1
    assert row["synced_quantity"] == 7
    assert row["last_error"] is None
    assert row["last_synced_at"] is not None
    assert "synced_price" not in row


async def test_force_pushes_everything_with_marketplace_ids():
    store = Store({"wildberries": [
        state(1, "A", synced_quantity=5, synced_price="100.00", external_product_id=11, external_size_id=22),
    ]})
    wb = FakeMarketplace()

    await make_service(store, {"wildberries": wb}).push_stocks_and_prices(force=True)

    assert wb.stock_calls == [[StockUpdate("A", 5, size_id=22)]]
    assert wb.price_calls == [[PriceUpdate("A", Decimal("100.00"), product_id=11)]]


async def test_rejected_item_keeps_old_synced_value_and_records_error():
    store = Store({"ozon": [state(1, "OK"), state(2, "BAD")]})
    before = metric("sfmshop_marketplace_sync_runs_total", marketplace="ozon", operation="push", result="partial")
    failed_before = metric("sfmshop_marketplace_items_total", marketplace="ozon", kind="stock", result="failed")

    results = await make_service(store, {"ozon": FakeMarketplace(rejected=["BAD"])}).push_stocks_and_prices()

    assert results["ozon"] == PushResult(stocks_updated=1, prices_updated=1, failed=1)
    ok, bad = store.saved
    assert ok["synced_quantity"] == 5 and ok["synced_price"] == Decimal("100.00")
    assert "synced_quantity" not in bad and "synced_price" not in bad
    assert "last_synced_at" not in bad
    assert bad["last_error"] == "остаток: TOO_MANY_REQUESTS: wait; цена: TOO_MANY_REQUESTS: wait"
    assert metric("sfmshop_marketplace_sync_runs_total", marketplace="ozon", operation="push",
                  result="partial") == before + 1
    assert metric("sfmshop_marketplace_items_total", marketplace="ozon", kind="stock",
                  result="failed") == failed_before + 1


async def test_item_missing_in_response_is_an_error():
    store = Store({"ozon": [state(1, "GONE", synced_price="100.00")]})

    await make_service(store, {"ozon": FakeMarketplace(missing=["GONE"])}).push_stocks_and_prices()

    assert store.saved[0]["last_error"] == "остаток: нет в ответе площадки"


async def test_failure_of_one_marketplace_does_not_stop_another():
    store = Store({"ozon": [state(1, "A")], "wildberries": [state(2, "B")]})
    ozon = FakeMarketplace(fail=MarketplaceUnavailableError("ozon временно недоступен: http_503"))
    wb = FakeMarketplace()
    before = metric("sfmshop_marketplace_sync_runs_total", marketplace="ozon", operation="push", result="error")

    results = await make_service(store, {"ozon": ozon, "wildberries": wb}).push_stocks_and_prices()

    assert results["ozon"] == PushResult(error="ozon временно недоступен: http_503")
    assert results["wildberries"] == PushResult(stocks_updated=1, prices_updated=1)
    assert store.errors == {"ozon": "ozon временно недоступен: http_503"}
    assert [row["id"] for row in store.saved] == [2]
    assert metric("sfmshop_marketplace_sync_runs_total", marketplace="ozon", operation="push",
                  result="error") == before + 1


async def test_unexpected_client_bug_is_isolated_too():
    store = Store({"ozon": [state(1, "A")], "wildberries": [state(2, "B")]})

    results = await make_service(store, {
        "ozon": FakeMarketplace(fail=KeyError("result")),
        "wildberries": FakeMarketplace(),
    }).push_stocks_and_prices()

    assert results["ozon"].error == "'result'"
    assert results["wildberries"].stocks_updated == 1


async def test_nothing_to_push_makes_no_requests():
    store = Store({"ozon": [state(1, "A", synced_quantity=5, synced_price="100.00")]})
    ozon = FakeMarketplace()

    results = await make_service(store, {"ozon": ozon}).push_stocks_and_prices()

    assert results["ozon"] == PushResult()
    assert ozon.stock_calls == [] and ozon.price_calls == []
    assert store.saved == []
