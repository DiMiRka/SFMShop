import asyncio
import os
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from sfmshop.core.config import app_settings
from sfmshop.database.connection import create_sessionmaker
from sfmshop.database.models import MarketplaceListing, Product
from sfmshop.repositories.marketplace_listing_repository import MarketplaceListingRepository
from sfmshop.services.marketplace_sync_service import MarketplaceSyncService
from tests.test_marketplace_sync import FakeMarketplace


pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_INTEGRATION_TESTS"),
    reason="нужен PostgreSQL после миграций (в CI задаётся RUN_INTEGRATION_TESTS=1)",
)


def test_push_saves_synced_values_and_listings_follow_product_lifecycle():
    async def scenario():
        engine = create_async_engine(app_settings.postgres_url)
        session_factory = create_sessionmaker(engine)
        marketplace = f"test-{uuid.uuid4().hex[:8]}"
        try:
            async with session_factory() as session:
                product = Product(name=f"Чайник {marketplace}", price=Decimal("1490.00"), quantity=4)
                session.add(product)
                await session.flush()
                session.add(MarketplaceListing(product_id=product.id, marketplace=marketplace, offer_id="KETTLE-1"))
                await session.commit()
                product_id = product.id

            client = FakeMarketplace()
            service = MarketplaceSyncService(session_factory, {marketplace: client})
            first = await service.push_stocks_and_prices()
            second = await service.push_stocks_and_prices()

            async with session_factory() as session:
                listing = await session.scalar(
                    select(MarketplaceListing).where(MarketplaceListing.marketplace == marketplace))
                session.add(MarketplaceListing(product_id=product_id, marketplace=marketplace, offer_id="KETTLE-1"))
                try:
                    await session.commit()
                    duplicate_rejected = False
                except IntegrityError:
                    await session.rollback()
                    duplicate_rejected = True

                await MarketplaceListingRepository(session).set_error(marketplace, "ozon недоступен")
                await session.commit()
                with_error = await session.scalar(
                    select(MarketplaceListing.last_error).where(MarketplaceListing.marketplace == marketplace))

                await session.execute(delete(Product).where(Product.id == product_id))
                await session.commit()
                left = await session.scalar(
                    select(MarketplaceListing.id).where(MarketplaceListing.marketplace == marketplace))

            return first, second, client, listing, duplicate_rejected, with_error, left
        finally:
            await engine.dispose()

    first, second, client, listing, duplicate_rejected, with_error, left = asyncio.run(scenario())

    [first_result] = first.values()
    [second_result] = second.values()
    assert (first_result.stocks_updated, first_result.prices_updated) == (1, 1)
    assert (second_result.stocks_updated, second_result.prices_updated) == (0, 0)
    assert len(client.stock_calls) == 1
    assert listing.synced_quantity == 4
    assert listing.synced_price == Decimal("1490.00")
    assert listing.last_synced_at is not None
    assert listing.last_error is None
    assert duplicate_rejected
    assert with_error == "ozon недоступен"
    assert left is None
