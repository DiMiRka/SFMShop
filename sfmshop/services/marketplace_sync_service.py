import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from sfmshop.clients.marketplaces import MarketplaceClient, PriceUpdate, StockUpdate, UpdateResult
from sfmshop.core.metrics import MARKETPLACE_ITEMS, MARKETPLACE_SYNC_DURATION, MARKETPLACE_SYNC_RUNS
from sfmshop.repositories.marketplace_listing_repository import ListingState, MarketplaceListingRepository
from sfmshop.services.log_service import log_service


MISSING_IN_RESPONSE = "нет в ответе площадки"


@dataclass(frozen=True)
class PushResult:
    stocks_updated: int = 0
    prices_updated: int = 0
    failed: int = 0
    error: str | None = None


class MarketplaceSyncService:
    def __init__(
            self,
            session_factory: Callable[[], AsyncSession],
            clients: dict[str, MarketplaceClient],
            listings_repository: Callable[[AsyncSession], MarketplaceListingRepository] = MarketplaceListingRepository):
        self.session_factory = session_factory
        self.clients = clients
        self.listings_repository = listings_repository

    async def push_stocks_and_prices(self, force: bool = False) -> dict[str, PushResult]:
        return {marketplace: await self._push_safely(marketplace, client, force)
                for marketplace, client in self.clients.items()}

    async def _push_safely(self, marketplace: str, client: MarketplaceClient, force: bool) -> PushResult:
        started = time.perf_counter()
        try:
            result = await self._push(marketplace, client, force)
        except Exception as exc:
            log_service.error("marketplace_push_failed", exception=exc, marketplace=marketplace)
            error = str(exc) or type(exc).__name__
            result = PushResult(error=error)
            async with self.session_factory() as session:
                await self.listings_repository(session).set_error(marketplace, error)
                await session.commit()

        outcome = "error" if result.error else "partial" if result.failed else "ok"
        MARKETPLACE_SYNC_RUNS.labels(marketplace, "push", outcome).inc()
        MARKETPLACE_SYNC_DURATION.labels(marketplace, "push").observe(time.perf_counter() - started)
        return result

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
