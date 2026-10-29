from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Protocol


class Marketplace(StrEnum):
    OZON = "ozon"
    WILDBERRIES = "wildberries"


@dataclass(frozen=True)
class StockUpdate:
    offer_id: str
    quantity: int
    size_id: int | None = None


@dataclass(frozen=True)
class PriceUpdate:
    offer_id: str
    price: Decimal
    product_id: int | None = None


@dataclass(frozen=True)
class UpdateResult:
    offer_id: str
    updated: bool
    error: str | None = None


@dataclass(frozen=True)
class MarketplaceOrderItem:
    offer_id: str
    quantity: int
    price: Decimal


@dataclass(frozen=True)
class MarketplaceOrder:
    external_id: str
    status: str
    created_at: datetime
    items: list[MarketplaceOrderItem]

    @property
    def total(self) -> Decimal:
        return sum((item.price * item.quantity for item in self.items), Decimal("0"))


class MarketplaceClient(Protocol):
    marketplace: Marketplace

    async def update_stocks(self, stocks: list[StockUpdate]) -> list[UpdateResult]:
        ...

    async def update_prices(self, prices: list[PriceUpdate]) -> list[UpdateResult]:
        ...

    async def fetch_orders(self, since: datetime) -> list[MarketplaceOrder]:
        ...

    async def close(self) -> None:
        ...
