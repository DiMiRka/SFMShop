from sqlalchemy.exc import IntegrityError

from sfmshop.core.exceptions import BusinessLogicError, NotFoundError
from sfmshop.repositories import ProductRepository
from sfmshop.repositories.marketplace_listing_repository import MarketplaceListingRepository
from sfmshop.schemas.marketplaces import ListingCreate, ListingResponse


class MarketplaceListingService:
    def __init__(self, listing_rep: MarketplaceListingRepository, product_rep: ProductRepository):
        self.listing_rep = listing_rep
        self.product_rep = product_rep

    async def list_listings(self, marketplace: str | None) -> list[dict]:
        listings = await self.listing_rep.get_all(marketplace)
        return [ListingResponse.model_validate(listing).model_dump(mode="json") for listing in listings]

    async def create_listing(self, listing: ListingCreate) -> dict:
        try:
            async with self.listing_rep.db.begin():
                if not await self.product_rep.get_by_id(listing.product_id):
                    raise NotFoundError("Товар не найден")
                listing_db = await self.listing_rep.create(listing.model_dump(mode="json"))
        except IntegrityError as exc:
            if "uq_marketplace_listings" not in str(exc.orig):
                raise
            raise BusinessLogicError("Товар или артикул уже привязан к этой площадке")

        return ListingResponse.model_validate(listing_db).model_dump(mode="json")

    async def delete_listing(self, listing_id: int) -> None:
        async with self.listing_rep.db.begin():
            listing = await self.listing_rep.get_by_id(listing_id)
            if listing is None:
                raise NotFoundError("Привязка не найдена")
            await self.listing_rep.delete(listing)
