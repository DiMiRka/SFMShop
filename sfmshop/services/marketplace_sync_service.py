import time
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from sfmshop.clients.marketplaces import MarketplaceClient, MarketplaceOrder, PriceUpdate, StockUpdate, UpdateResult
from sfmshop.core.metrics import (MARKETPLACE_ITEMS, MARKETPLACE_ORDERS, MARKETPLACE_SYNC_DURATION,
                                  MARKETPLACE_SYNC_RUNS)
from sfmshop.repositories.marketplace_listing_repository import ListingState, MarketplaceListingRepository
from sfmshop.repositories.marketplace_order_repository import MarketplaceOrderRepository
from sfmshop.repositories.product_repository import ProductRepository
from sfmshop.services.log_service import log_service
from sfmshop.services.queue_producer import QueueProducer


MISSING_IN_RESPONSE = "нет в ответе площадки"
CANCELLED_STATUSES = frozenset({
    "cancelled", "canceled", "canceled_by_client", "declined_by_client", "canceled_by_carrier", "defect",
})

Result = TypeVar("Result", "PushResult", "ImportResult")


@dataclass(frozen=True)
class PushResult:
    stocks_updated: int = 0
    prices_updated: int = 0
    failed: int = 0
    error: str | None = None


@dataclass(frozen=True)
class ImportResult:
    imported: int = 0
    duplicates: int = 0
    unmatched_items: int = 0
    error: str | None = None


class MarketplaceSyncService:
    def __init__(
            self,
            session_factory: Callable[[], AsyncSession],
            clients: dict[str, MarketplaceClient],
            queue: QueueProducer,
            orders_lookback: timedelta = timedelta(hours=24),
            orders_overlap: timedelta = timedelta(hours=1),
            listings_repository: Callable[[AsyncSession], MarketplaceListingRepository] = MarketplaceListingRepository,
            orders_repository: Callable[[AsyncSession], MarketplaceOrderRepository] = MarketplaceOrderRepository,
            products_repository: Callable[[AsyncSession], ProductRepository] = ProductRepository):
        self.session_factory = session_factory
        self.clients = clients
        self.queue = queue
        self.orders_lookback = orders_lookback
        self.orders_overlap = orders_overlap
        self.listings_repository = listings_repository
        self.orders_repository = orders_repository
        self.products_repository = products_repository

    async def push_stocks_and_prices(self, force: bool = False) -> dict[str, PushResult]:
        results = {}
        for marketplace, client in self.clients.items():
            results[marketplace] = await self._safely(
                marketplace, "push", lambda: self._push(marketplace, client, force), self._push_failed)
        return results

    async def import_orders(self) -> dict[str, ImportResult]:
        results = {}
        for marketplace, client in self.clients.items():
            results[marketplace] = await self._safely(
                marketplace, "orders", lambda: self._import(marketplace, client), self._import_failed)
        return results

    async def _safely(
            self,
            marketplace: str,
            operation: str,
            action: Callable[[], Awaitable[Result]],
            on_error: Callable[[str, str], Awaitable[Result]]) -> Result:
        started = time.perf_counter()
        try:
            result = await action()
        except Exception as exc:
            log_service.error("marketplace_sync_failed", exception=exc, marketplace=marketplace, operation=operation)
            result = await on_error(marketplace, str(exc) or type(exc).__name__)

        outcome = "error" if result.error else "partial" if getattr(result, "failed", 0) else "ok"
        MARKETPLACE_SYNC_RUNS.labels(marketplace, operation, outcome).inc()
        MARKETPLACE_SYNC_DURATION.labels(marketplace, operation).observe(time.perf_counter() - started)
        return result

    async def _push_failed(self, marketplace: str, error: str) -> PushResult:
        async with self.session_factory() as session:
            await self.listings_repository(session).set_error(marketplace, error)
            await session.commit()
        return PushResult(error=error)

    @staticmethod
    async def _import_failed(marketplace: str, error: str) -> ImportResult:
        return ImportResult(error=error)

    async def _push(self, marketplace: str, client: MarketplaceClient, force: bool) -> PushResult:
        async with self.session_factory() as session:
            listings = await self.listings_repository(session).get_states(marketplace)

        stocks = [listing for listing in listings if force or listing.quantity != listing.synced_quantity]
        prices = [listing for listing in listings if force or listing.price != listing.synced_price]
        stock_results = by_offer(await client.update_stocks([
            StockUpdate(listing.offer_id, listing.quantity, size_id=listing.external_size_id) for listing in stocks
        ])) if stocks else {}
        price_results = by_offer(await client.update_prices([
            PriceUpdate(listing.offer_id, listing.price, product_id=listing.external_product_id) for listing in prices
        ])) if prices else {}

        now = datetime.now(UTC)
        stock_ids = {listing.id for listing in stocks}
        price_ids = {listing.id for listing in prices}
        rows = []
        for listing in listings:
            if listing.id not in stock_ids and listing.id not in price_ids:
                continue
            row, errors = sync_row(listing, stock_results if listing.id in stock_ids else None,
                                   price_results if listing.id in price_ids else None)
            row["last_error"] = "; ".join(errors) or None
            if not errors:
                row["last_synced_at"] = now
            rows.append(row)

        async with self.session_factory() as session:
            await self.listings_repository(session).save_results(rows)
            await session.commit()

        stocks_updated = sum("synced_quantity" in row for row in rows)
        prices_updated = sum("synced_price" in row for row in rows)
        MARKETPLACE_ITEMS.labels(marketplace, "stock", "updated").inc(stocks_updated)
        MARKETPLACE_ITEMS.labels(marketplace, "stock", "failed").inc(len(stocks) - stocks_updated)
        MARKETPLACE_ITEMS.labels(marketplace, "price", "updated").inc(prices_updated)
        MARKETPLACE_ITEMS.labels(marketplace, "price", "failed").inc(len(prices) - prices_updated)
        result = PushResult(stocks_updated=stocks_updated, prices_updated=prices_updated,
                            failed=sum(row["last_error"] is not None for row in rows))
        log_service.info("marketplace_pushed", marketplace=marketplace, stocks=stocks_updated,
                         prices=prices_updated, failed=result.failed)
        return result

    async def _import(self, marketplace: str, client: MarketplaceClient) -> ImportResult:
        async with self.session_factory() as session:
            last_ordered_at = await self.orders_repository(session).last_ordered_at(marketplace)

        since = (last_ordered_at - self.orders_overlap if last_ordered_at is not None
                 else datetime.now(UTC) - self.orders_lookback)
        orders = list({order.external_id: order for order in await client.fetch_orders(since)}.values())
        if not orders:
            return ImportResult()

        async with self.session_factory() as session:
            product_ids = await self.listings_repository(session).get_product_ids(
                marketplace, sorted({item.offer_id for order in orders for item in order.items}))
            inserted = await self.orders_repository(session).insert_new(
                [order_row(marketplace, order, product_ids) for order in orders])
            new_orders = [order for order in orders if order.external_id in inserted]
            sold = sold_quantities(new_orders, product_ids)
            if sold:
                await self.products_repository(session).subtract_quantities(sold)
            await session.commit()

        if new_orders:
            await self.queue.publish_event("order_exchange", "marketplace.orders_imported", {
                "marketplace": marketplace,
                "external_ids": [order.external_id for order in new_orders],
                "product_ids": sorted(sold),
                "actor_role": "system",
            })

        result = ImportResult(
            imported=len(new_orders),
            duplicates=len(orders) - len(new_orders),
            unmatched_items=sum(item.offer_id not in product_ids for order in new_orders for item in order.items),
        )
        MARKETPLACE_ORDERS.labels(marketplace, "imported").inc(result.imported)
        MARKETPLACE_ORDERS.labels(marketplace, "duplicate").inc(result.duplicates)
        log_service.info("marketplace_orders_imported", marketplace=marketplace, imported=result.imported,
                         duplicates=result.duplicates, unmatched_items=result.unmatched_items)
        return result


def by_offer(results: list[UpdateResult]) -> dict[str, UpdateResult]:
    return {result.offer_id: result for result in results}


def sync_row(
        listing: ListingState,
        stock_results: dict[str, UpdateResult] | None,
        price_results: dict[str, UpdateResult] | None) -> tuple[dict[str, Any], list[str]]:
    row: dict[str, Any] = {"id": listing.id}
    errors = []
    if stock_results is not None:
        stock = stock_results.get(listing.offer_id)
        if stock is not None and stock.updated:
            row["synced_quantity"] = listing.quantity
        else:
            errors.append(f"остаток: {stock.error if stock else MISSING_IN_RESPONSE}")
    if price_results is not None:
        price = price_results.get(listing.offer_id)
        if price is not None and price.updated:
            row["synced_price"] = listing.price
        else:
            errors.append(f"цена: {price.error if price else MISSING_IN_RESPONSE}")
    return row, errors


def order_row(marketplace: str, order: MarketplaceOrder, product_ids: dict[str, int]) -> dict[str, Any]:
    return {
        "marketplace": marketplace,
        "external_id": order.external_id,
        "status": order.status,
        "total": order.total,
        "ordered_at": order.created_at,
        "items": [
            {"offer_id": item.offer_id, "product_id": product_ids.get(item.offer_id),
             "quantity": item.quantity, "price": str(item.price)}
            for item in order.items
        ],
    }


def sold_quantities(orders: list[MarketplaceOrder], product_ids: dict[str, int]) -> dict[int, int]:
    sold: Counter[int] = Counter()
    for order in orders:
        if order.status in CANCELLED_STATUSES:
            continue
        for item in order.items:
            if item.offer_id in product_ids:
                sold[product_ids[item.offer_id]] += item.quantity
    return dict(sold)
