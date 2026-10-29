from datetime import datetime
from decimal import Decimal
from typing import Self

from pydantic import ConfigDict, Field, model_validator

from sfmshop.clients.marketplaces import Marketplace
from sfmshop.schemas.base import Base


class ListingCreate(Base):
    product_id: int = Field(..., ge=1)
    marketplace: Marketplace
    offer_id: str = Field(..., min_length=1, max_length=100, description="Артикул продавца на площадке")
    external_product_id: int | None = Field(None, ge=1, description="nmID на Wildberries")
    external_size_id: int | None = Field(None, ge=1, description="chrtId размера на Wildberries")

    model_config = ConfigDict(str_strip_whitespace=True)

    @model_validator(mode="after")
    def wildberries_needs_ids(self) -> Self:
        if self.marketplace == Marketplace.WILDBERRIES and (
                self.external_product_id is None or self.external_size_id is None):
            raise ValueError("Для Wildberries нужны external_product_id (nmID) и external_size_id (chrtId)")
        return self


class ListingResponse(Base):
    id: int
    product_id: int
    marketplace: str
    offer_id: str
    external_product_id: int | None
    external_size_id: int | None
    synced_quantity: int | None
    synced_price: Decimal | None
    last_synced_at: datetime | None
    last_error: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
