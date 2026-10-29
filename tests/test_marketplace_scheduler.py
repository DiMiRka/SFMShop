import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from sfmshop.api.main import sfmshop_app as app
from sfmshop.clients.marketplaces import Marketplace
from sfmshop.core import dependencies
from sfmshop.core.exceptions import BusinessLogicError, MarketplaceSyncBusyError, NotFoundError
from sfmshop.schemas.marketplaces import ListingCreate
from sfmshop.services import marketplace_scheduler
from sfmshop.services.marketplace_listing_service import MarketplaceListingService
from sfmshop.services.marketplace_scheduler import MarketplaceSyncRunner, SyncReport
from sfmshop.services.marketplace_sync_service import ImportResult, PushResult
from tests.test_queue import FakeMessage, build_consumer


client = TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


class FakeSyncService:
    def __init__(self, fail=None):
        self.calls = []
        self.fail = fail

    async def import_orders(self):
        self.calls.append("orders")
        if self.fail:
            raise self.fail
        return {"ozon": ImportResult(imported=1)}

    async def push_stocks_and_prices(self, force=False):
        self.calls.append(("push", force))
        return {"ozon": PushResult(stocks_updated=2)}


def lock(acquired=True):
    @asynccontextmanager
    async def fake_lock():
        yield acquired

    return fake_lock


@pytest.mark.anyio
async def test_run_once_imports_orders_before_pushing_stocks():
    service = FakeSyncService()

    report = await MarketplaceSyncRunner(service, lock(), interval=60).run_once(force=True)

    assert service.calls == ["orders", ("push", True)]
    assert report == SyncReport(orders={"ozon": ImportResult(imported=1)},
                                stocks_and_prices={"ozon": PushResult(stocks_updated=2)})


@pytest.mark.anyio
async def test_run_once_refuses_when_another_worker_holds_the_lock():
    service = FakeSyncService()

    with pytest.raises(MarketplaceSyncBusyError):
        await MarketplaceSyncRunner(service, lock(acquired=False), interval=60).run_once()

    assert service.calls == []


@pytest.mark.anyio
async def test_run_forever_survives_errors_and_waits_interval(monkeypatch):
    service = FakeSyncService(fail=RuntimeError("boom"))
    sleeps = []

    async def fake_sleep(delay):
        sleeps.append(delay)
        if len(sleeps) == 3:
            raise asyncio.CancelledError

    monkeypatch.setattr(marketplace_scheduler.asyncio, "sleep", fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        await MarketplaceSyncRunner(service, lock(), interval=300).run_forever()

    assert sleeps == [300, 300, 300]
    assert service.calls == ["orders"] * 3


@pytest.mark.anyio
async def test_imported_orders_event_invalidates_product_cache():
    consumer, cache = build_consumer()

    await consumer.process_cache_event(FakeMessage("marketplace.orders_imported", {
        "marketplace": "ozon", "external_ids": ["1-1"], "product_ids": [10, 20], "actor_role": "system",
    }))

    cache.delete_products.assert_awaited_once_with([10, 20])
    cache.delete_orders.assert_not_awaited()


async def admin():
    return SimpleNamespace(id=1, is_admin=True)


async def customer():
    return SimpleNamespace(id=2, is_admin=False)


def fake_runner(report=None, error=None):
    runner = MagicMock()
    runner.run_once = AsyncMock(return_value=report, side_effect=error)
    return runner


def test_sync_endpoint_returns_report_for_admin():
    runner = fake_runner(SyncReport(orders={"ozon": ImportResult(imported=1)},
                                    stocks_and_prices={"ozon": PushResult(stocks_updated=2)}))
    app.dependency_overrides[dependencies.get_current_user] = admin
    app.dependency_overrides[dependencies.get_marketplace_sync_runner] = lambda: runner

    response = client.post("/v1/marketplaces/sync?force=true")

    assert response.status_code == 200
    assert response.json() == {
        "orders": {"ozon": {"imported": 1, "duplicates": 0, "unmatched_items": 0, "error": None}},
        "stocks_and_prices": {"ozon": {"stocks_updated": 2, "prices_updated": 0, "failed": 0, "error": None}},
    }
    runner.run_once.assert_awaited_once_with(force=True)


def test_sync_endpoint_conflict_when_already_running():
    app.dependency_overrides[dependencies.get_current_user] = admin
    app.dependency_overrides[dependencies.get_marketplace_sync_runner] = lambda: fake_runner(
        error=MarketplaceSyncBusyError("Синхронизация с маркетплейсами уже выполняется"))

    response = client.post("/v1/marketplaces/sync")

    assert response.status_code == 409


def test_sync_endpoint_unavailable_without_marketplace_keys():
    app.dependency_overrides[dependencies.get_current_user] = admin

    response = client.post("/v1/marketplaces/sync")

    assert response.status_code == 503


def test_sync_endpoint_is_admin_only():
    app.dependency_overrides[dependencies.get_current_user] = customer
    app.dependency_overrides[dependencies.get_marketplace_sync_runner] = lambda: fake_runner()

    response = client.post("/v1/marketplaces/sync")

    assert response.status_code == 403


def test_wildberries_listing_requires_marketplace_ids():
    service = MagicMock()
    service.create_listing = AsyncMock()
    app.dependency_overrides[dependencies.get_current_user] = admin
    app.dependency_overrides[dependencies.get_marketplace_listing_write_service] = lambda: service

    response = client.post("/v1/marketplaces/listings",
                           json={"product_id": 1, "marketplace": "wildberries", "offer_id": "SKU-1"})

    assert response.status_code == 422
    service.create_listing.assert_not_awaited()


def test_ozon_listing_is_created():
    service = MagicMock()
    service.create_listing = AsyncMock(return_value={
        "id": 5, "product_id": 1, "marketplace": "ozon", "offer_id": "SKU-1", "external_product_id": None,
        "external_size_id": None, "synced_quantity": None, "synced_price": None, "last_synced_at": None,
        "last_error": None, "created_at": "2026-10-29T12:00:00",
    })
    app.dependency_overrides[dependencies.get_current_user] = admin
    app.dependency_overrides[dependencies.get_marketplace_listing_write_service] = lambda: service

    response = client.post("/v1/marketplaces/listings",
                           json={"product_id": 1, "marketplace": "ozon", "offer_id": " SKU-1 "})

    assert response.status_code == 201
    assert response.json()["id"] == 5
    [listing] = service.create_listing.await_args.args
    assert listing.offer_id == "SKU-1"


class Transaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def listing_service(product=True, create_error=None):
    listing_rep = MagicMock()
    listing_rep.db.begin = Transaction
    listing_rep.create = AsyncMock(side_effect=create_error)
    product_rep = MagicMock()
    product_rep.get_by_id = AsyncMock(return_value=SimpleNamespace(id=1) if product else None)
    return MarketplaceListingService(listing_rep, product_rep), listing_rep


OZON_LISTING = ListingCreate(product_id=1, marketplace=Marketplace.OZON, offer_id="SKU-1")


@pytest.mark.anyio
async def test_listing_for_missing_product_is_not_found():
    service, listing_rep = listing_service(product=False)

    with pytest.raises(NotFoundError):
        await service.create_listing(OZON_LISTING)

    listing_rep.create.assert_not_awaited()


@pytest.mark.anyio
async def test_duplicate_listing_is_a_conflict():
    error = IntegrityError("INSERT", {}, Exception('duplicate key violates "uq_marketplace_listings_offer"'))
    service, _ = listing_service(create_error=error)

    with pytest.raises(BusinessLogicError, match="уже привязан"):
        await service.create_listing(OZON_LISTING)
