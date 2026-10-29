import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from sfmshop.core.exceptions import MarketplaceSyncBusyError
from sfmshop.services.log_service import log_service
from sfmshop.services.marketplace_sync_service import ImportResult, MarketplaceSyncService, PushResult


SYNC_LOCK_KEY = 7_340_001


@dataclass(frozen=True)
class SyncReport:
    orders: dict[str, ImportResult]
    stocks_and_prices: dict[str, PushResult]


@asynccontextmanager
async def advisory_lock(engine: AsyncEngine, key: int = SYNC_LOCK_KEY) -> AsyncIterator[bool]:
    async with engine.connect() as connection:
        connection = await connection.execution_options(isolation_level="AUTOCOMMIT")
        acquired = bool(await connection.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": key}))
        try:
            yield acquired
        finally:
            if acquired:
                await connection.scalar(text("SELECT pg_advisory_unlock(:key)"), {"key": key})


class MarketplaceSyncRunner:
    def __init__(
            self,
            service: MarketplaceSyncService,
            lock: Callable[[], AbstractAsyncContextManager[bool]],
            interval: float):
        self.service = service
        self.lock = lock
        self.interval = interval

    async def run_once(self, force: bool = False) -> SyncReport:
        async with self.lock() as acquired:
            if not acquired:
                raise MarketplaceSyncBusyError("Синхронизация с маркетплейсами уже выполняется")
            orders = await self.service.import_orders()
            stocks_and_prices = await self.service.push_stocks_and_prices(force=force)
        return SyncReport(orders=orders, stocks_and_prices=stocks_and_prices)

    async def run_forever(self) -> None:
        while True:
            try:
                await self.run_once()
            except MarketplaceSyncBusyError:
                log_service.info("marketplace_sync_skipped", reason="locked")
            except Exception as exc:
                log_service.error("marketplace_sync_crashed", exception=exc)
            await asyncio.sleep(self.interval)
