from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from sfmshop.database.models import MarketplaceListing, Product


@dataclass(frozen=True)
class ListingState:
    id: int
    offer_id: str
    external_product_id: int | None
    external_size_id: int | None
    synced_quantity: int | None
    synced_price: Decimal | None
    quantity: int
    price: Decimal


class MarketplaceListingRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_states(self, marketplace: str) -> list[ListingState]:
        result = await self.db.execute(
            select(
                MarketplaceListing.id,
                MarketplaceListing.offer_id,
                MarketplaceListing.external_product_id,
                MarketplaceListing.external_size_id,
                MarketplaceListing.synced_quantity,
                MarketplaceListing.synced_price,
                Product.quantity,
                Product.price,
            )
            .join(Product, Product.id == MarketplaceListing.product_id)
            .where(MarketplaceListing.marketplace == marketplace)
            .order_by(MarketplaceListing.id)
        )
        return [ListingState(**row._mapping) for row in result]

    async def save_results(self, rows: list[dict[str, Any]]) -> None:
        if rows:
            await self.db.execute(update(MarketplaceListing), rows)

    async def set_error(self, marketplace: str, error: str) -> None:
        await self.db.execute(
            update(MarketplaceListing).where(MarketplaceListing.marketplace == marketplace).values(last_error=error)
        )
