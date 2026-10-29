import asyncio
import os
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import create_async_engine

from sfmshop.core.config import app_settings
from sfmshop.database.connection import create_sessionmaker
from sfmshop.database.models import ImportedOrder, MarketplaceListing, Product
from sfmshop.services.marketplace_scheduler import advisory_lock
from sfmshop.services.marketplace_sync_service import MarketplaceSyncService
from tests.test_marketplace_sync import FakeMarketplace, order
from tests.test_services import FakeQueue


pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_INTEGRATION_TESTS"),
    reason="нужен PostgreSQL после миграций (в CI задаётся RUN_INTEGRATION_TESTS=1)",
)


def test_repeated_import_does_not_duplicate_orders_or_subtract_stock_twice():
    async def scenario():
        engine = create_async_engine(app_settings.postgres_url)
        session_factory = create_sessionmaker(engine)
        marketplace = f"test-{uuid.uuid4().hex[:8]}"
        try:
            async with session_factory() as session:
                product = Product(name=f"Лампа {marketplace}", price=Decimal("500.00"), quantity=3)
                session.add(product)
                await session.flush()
                session.add(MarketplaceListing(product_id=product.id, marketplace=marketplace, offer_id="LAMP"))
                await session.commit()
                product_id = product.id

            client = FakeMarketplace(orders=[order("100", ("LAMP", 2, "500")), order("101", ("LAMP", 5, "500"))])
            service = MarketplaceSyncService(session_factory, {marketplace: client}, FakeQueue(),
                                             orders_overlap=timedelta(hours=1))
            first = await service.import_orders()
            second = await service.import_orders()

            async with session_factory() as session:
                quantity = await session.scalar(select(Product.quantity).where(Product.id == product_id))
                stored = await session.scalar(
                    select(func.count()).select_from(ImportedOrder).where(ImportedOrder.marketplace == marketplace))
                await session.execute(delete(ImportedOrder).where(ImportedOrder.marketplace == marketplace))
                await session.execute(delete(Product).where(Product.id == product_id))
                await session.commit()

            return first[marketplace], second[marketplace], client.order_calls, quantity, stored
        finally:
            await engine.dispose()

    first, second, order_calls, quantity, stored = asyncio.run(scenario())

    assert (first.imported, first.duplicates) == (2, 0)
    assert (second.imported, second.duplicates) == (0, 2)
    assert order_calls[1] == order("100").created_at - timedelta(hours=1)
    assert quantity == 0
    assert stored == 2


def test_advisory_lock_lets_only_one_runner_in():
    async def scenario():
        engine = create_async_engine(app_settings.postgres_url)
        key = 7_000_000 + uuid.uuid4().int % 1_000_000
        try:
            async with advisory_lock(engine, key) as first:
                async with advisory_lock(engine, key) as second:
                    pass
            async with advisory_lock(engine, key) as after_release:
                pass
            return first, second, after_release
        finally:
            await engine.dispose()

    assert asyncio.run(scenario()) == (True, False, True)
