from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from prometheus_client import REGISTRY

from sfmshop.clients.marketplaces import (MarketplaceOrder, MarketplaceOrderItem, PriceUpdate, StockUpdate,
                                          UpdateResult)
from sfmshop.core.exceptions import MarketplaceUnavailableError
from sfmshop.repositories.marketplace_listing_repository import ListingState
from sfmshop.services.marketplace_sync_service import ImportResult, MarketplaceSyncService, PushResult
from tests.test_services import FakeQueue


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
    def __init__(self, states=None, offers=None, last_ordered_at=None):
        self.states = states or {}
        self.offers = offers or {}
        self.last_ordered_at = last_ordered_at
        self.saved = []
        self.errors = {}
        self.orders = {}
        self.subtracted = []

    def repository(self, session):
        return FakeListingRepository(self)

    def orders_repository(self, session):
        return FakeOrderRepository(self)

    def products_repository(self, session):
        return FakeProductRepository(self)


class FakeListingRepository:
    def __init__(self, store):
        self.store = store

    async def get_states(self, marketplace):
        return self.store.states.get(marketplace, [])

    async def save_results(self, rows):
        self.store.saved += rows

    async def set_error(self, marketplace, error):
        self.store.errors[marketplace] = error

    async def get_product_ids(self, marketplace, offer_ids):
        return {offer_id: product_id for offer_id, product_id in self.store.offers.items() if offer_id in offer_ids}


class FakeOrderRepository:
    def __init__(self, store):
        self.store = store

    async def last_ordered_at(self, marketplace):
        return self.store.last_ordered_at

    async def insert_new(self, rows):
        inserted = set()
        for row in rows:
            key = (row["marketplace"], row["external_id"])
            if key not in self.store.orders:
                self.store.orders[key] = row
                inserted.add(row["external_id"])
        return inserted


class FakeProductRepository:
    def __init__(self, store):
        self.store = store

    async def subtract_quantities(self, quantities):
        self.store.subtracted.append((quantities, Session.commits))


class FakeMarketplace:
    def __init__(self, fail=None, rejected=(), missing=(), orders=()):
        self.fail = fail
        self.rejected = set(rejected)
        self.missing = set(missing)
        self.orders = list(orders)
        self.stock_calls = []
        self.price_calls = []
        self.order_calls = []

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

    async def fetch_orders(self, since):
        self.order_calls.append(since)
        if self.fail:
            raise self.fail
        return self.orders


def state(listing_id, offer_id, quantity=5, price="100.00", synced_quantity=None, synced_price=None,
          external_product_id=None, external_size_id=None):
    return ListingState(
        id=listing_id, offer_id=offer_id, external_product_id=external_product_id, external_size_id=external_size_id,
        synced_quantity=synced_quantity, synced_price=Decimal(synced_price) if synced_price else None,
        quantity=quantity, price=Decimal(price),
    )


def make_service(store, clients, queue=None):
    return MarketplaceSyncService(
        Session, clients, queue or FakeQueue(),
        orders_lookback=timedelta(hours=24),
        orders_overlap=timedelta(hours=1),
        listings_repository=store.repository,
        orders_repository=store.orders_repository,
        products_repository=store.products_repository,
    )


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


def order(external_id, *items, status="awaiting_packaging"):
    return MarketplaceOrder(
        external_id=external_id,
        status=status,
        created_at=datetime(2026, 10, 29, 10, 0, tzinfo=UTC),
        items=[MarketplaceOrderItem(offer_id, quantity, Decimal(price)) for offer_id, quantity, price in items],
    )


async def test_import_saves_new_orders_and_subtracts_stock_once():
    store = Store(offers={"A": 10, "B": 20})
    ozon = FakeMarketplace(orders=[order("1-1", ("A", 2, "100.50"), ("B", 1, "10.00")),
                                   order("2-1", ("A", 1, "100.50"))])
    queue = FakeQueue()
    service = make_service(store, {"ozon": ozon}, queue)

    first = await service.import_orders()
    second = await service.import_orders()

    assert first == {"ozon": ImportResult(imported=2)}
    assert second == {"ozon": ImportResult(duplicates=2)}
    assert [quantities for quantities, _ in store.subtracted] == [{10: 3, 20: 1}]
    saved = store.orders[("ozon", "1-1")]
    assert saved["total"] == Decimal("211.00")
    assert saved["ordered_at"] == datetime(2026, 10, 29, 10, 0, tzinfo=UTC)
    assert saved["items"][0] == {"offer_id": "A", "product_id": 10, "quantity": 2, "price": "100.50"}
    assert len(queue.events) == 1


async def test_import_publishes_event_after_commit():
    store = Store(offers={"A": 10})
    queue = FakeQueue()
    commits_at_publish = []
    original = queue.publish_event

    async def publish_event(*args, **kwargs):
        commits_at_publish.append(Session.commits)
        return await original(*args, **kwargs)

    queue.publish_event = publish_event
    await make_service(store, {"ozon": FakeMarketplace(orders=[order("1-1", ("A", 1, "5"))])}, queue).import_orders()

    [(_, commits_before_subtract)] = store.subtracted
    assert commits_at_publish == [commits_before_subtract + 1]
    assert queue.events == [("order_exchange", "marketplace.orders_imported", {
        "marketplace": "ozon", "external_ids": ["1-1"], "product_ids": [10], "actor_role": "system",
    })]


async def test_cancelled_and_unlinked_items_do_not_change_stock():
    store = Store(offers={"A": 10})
    wb = FakeMarketplace(orders=[order("1", ("A", 1, "5"), status="canceled_by_client"),
                                 order("2", ("UNKNOWN", 1, "5"))])
    queue = FakeQueue()

    results = await make_service(store, {"wildberries": wb}, queue).import_orders()

    assert results["wildberries"] == ImportResult(imported=2, unmatched_items=1)
    assert store.subtracted == []
    assert store.orders[("wildberries", "2")]["items"][0]["product_id"] is None
    assert queue.events[0][2]["product_ids"] == []


async def test_import_window_overlaps_last_imported_order():
    last = datetime(2026, 10, 29, 9, 0, tzinfo=UTC)
    ozon = FakeMarketplace()

    await make_service(Store(last_ordered_at=last), {"ozon": ozon}).import_orders()

    assert ozon.order_calls == [last - timedelta(hours=1)]


async def test_first_import_looks_back_from_now():
    ozon = FakeMarketplace()

    await make_service(Store(), {"ozon": ozon}).import_orders()

    [since] = ozon.order_calls
    assert abs(datetime.now(UTC) - timedelta(hours=24) - since) < timedelta(minutes=1)


async def test_same_order_twice_in_one_response_is_counted_once():
    store = Store(offers={"A": 10})
    ozon = FakeMarketplace(orders=[order("1-1", ("A", 1, "5")), order("1-1", ("A", 1, "5"))])

    results = await make_service(store, {"ozon": ozon}).import_orders()

    assert results["ozon"] == ImportResult(imported=1)
    assert store.subtracted[0][0] == {10: 1}


async def test_import_failure_of_one_marketplace_does_not_stop_another():
    store = Store(offers={"B": 20})
    before = metric("sfmshop_marketplace_sync_runs_total", marketplace="ozon", operation="orders", result="error")

    results = await make_service(store, {
        "ozon": FakeMarketplace(fail=MarketplaceUnavailableError("ozon временно недоступен: http_503")),
        "wildberries": FakeMarketplace(orders=[order("7", ("B", 1, "5"))]),
    }).import_orders()

    assert results["ozon"] == ImportResult(error="ozon временно недоступен: http_503")
    assert results["wildberries"] == ImportResult(imported=1)
    assert metric("sfmshop_marketplace_sync_runs_total", marketplace="ozon", operation="orders",
                  result="error") == before + 1


async def test_no_new_orders_publishes_nothing():
    queue = FakeQueue()

    results = await make_service(Store(), {"ozon": FakeMarketplace()}, queue).import_orders()

    assert results["ozon"] == ImportResult()
    assert queue.events == []
