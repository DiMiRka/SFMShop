from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from sfmshop.database.models import ImportedOrder


class MarketplaceOrderRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def last_ordered_at(self, marketplace: str) -> datetime | None:
        return await self.db.scalar(
            select(func.max(ImportedOrder.ordered_at)).where(ImportedOrder.marketplace == marketplace)
        )

    async def insert_new(self, rows: list[dict[str, Any]]) -> set[str]:
        result = await self.db.execute(
            insert(ImportedOrder)
            .values(rows)
            .on_conflict_do_nothing(constraint="uq_marketplace_orders_external")
            .returning(ImportedOrder.external_id)
        )
        return set(result.scalars().all())
