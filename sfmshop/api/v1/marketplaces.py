from dataclasses import asdict

from fastapi import APIRouter, Query, status

from sfmshop.clients.marketplaces import Marketplace
from sfmshop.core.dependencies import (admin_user, marketplace_listing_read_service,
                                       marketplace_listing_write_service, marketplace_sync_runner)
from sfmshop.schemas.marketplaces import ListingCreate, ListingResponse

marketplaces_router = APIRouter(prefix="/marketplaces", tags=["marketplaces"])


@marketplaces_router.post("/sync", summary="Синхронизировать с маркетплейсами сейчас",
                          status_code=status.HTTP_200_OK)
async def sync_now(admin: admin_user, runner: marketplace_sync_runner,
                   force: bool = Query(False, description="Отправить все остатки и цены, а не только изменённые")):
    return asdict(await runner.run_once(force=force))


@marketplaces_router.get("/listings", summary="Привязки товаров к площадкам", status_code=status.HTTP_200_OK,
                         response_model=list[ListingResponse])
async def get_listings(admin: admin_user, service: marketplace_listing_read_service,
                       marketplace: Marketplace | None = None):
    return await service.list_listings(marketplace)


@marketplaces_router.post("/listings", summary="Привязать товар к площадке", status_code=status.HTTP_201_CREATED,
                          response_model=ListingResponse)
async def post_listing(admin: admin_user, service: marketplace_listing_write_service, listing: ListingCreate):
    return await service.create_listing(listing)


@marketplaces_router.delete("/listings/{listing_id}", summary="Удалить привязку",
                            status_code=status.HTTP_204_NO_CONTENT)
async def delete_listing(admin: admin_user, service: marketplace_listing_write_service, listing_id: int):
    await service.delete_listing(listing_id)
