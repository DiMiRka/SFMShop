from collections.abc import Callable

import httpx

from sfmshop.clients.marketplaces.base import (Marketplace, MarketplaceClient, MarketplaceOrder, MarketplaceOrderItem,
                                               PriceUpdate, StockUpdate, UpdateResult)
from sfmshop.clients.marketplaces.http import MarketplaceHttp
from sfmshop.clients.marketplaces.ozon import OzonClient
from sfmshop.clients.marketplaces.wildberries import WildberriesClient
from sfmshop.core.config import AppSettings


def build_ozon_client(settings: AppSettings) -> MarketplaceClient | None:
    if not (settings.ozon_client_id and settings.ozon_api_key and settings.ozon_warehouse_id):
        return None

    http_client = httpx.AsyncClient(
        base_url=settings.ozon_base_url,
        timeout=httpx.Timeout(settings.marketplace_timeout, connect=settings.marketplace_connect_timeout),
        headers={"Client-Id": settings.ozon_client_id, "Api-Key": settings.ozon_api_key},
    )
    http = MarketplaceHttp(Marketplace.OZON, http_client, max_retries=settings.marketplace_max_retries)
    return OzonClient(http, warehouse_id=settings.ozon_warehouse_id)


def build_wildberries_client(settings: AppSettings) -> MarketplaceClient | None:
    if not (settings.wb_api_token and settings.wb_warehouse_id):
        return None

    http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(settings.marketplace_timeout, connect=settings.marketplace_connect_timeout),
        headers={"Authorization": settings.wb_api_token},
    )
    http = MarketplaceHttp(Marketplace.WILDBERRIES, http_client, retry_after_header="X-Ratelimit-Retry",
                           max_retries=settings.marketplace_max_retries)
    return WildberriesClient(
        http,
        prices_url=settings.wb_prices_base_url,
        marketplace_url=settings.wb_marketplace_base_url,
        warehouse_id=settings.wb_warehouse_id,
    )


MARKETPLACE_PROVIDERS: dict[Marketplace, Callable[[AppSettings], MarketplaceClient | None]] = {
    Marketplace.OZON: build_ozon_client,
    Marketplace.WILDBERRIES: build_wildberries_client,
}


def create_marketplace_clients(settings: AppSettings) -> dict[Marketplace, MarketplaceClient]:
    clients = {}
    for marketplace, factory in MARKETPLACE_PROVIDERS.items():
        client = factory(settings)
        if client is not None:
            clients[marketplace] = client
    return clients


__all__ = [
    'Marketplace',
    'MarketplaceClient',
    'MarketplaceOrder',
    'MarketplaceOrderItem',
    'PriceUpdate',
    'StockUpdate',
    'UpdateResult',
    'OzonClient',
    'WildberriesClient',
    'MARKETPLACE_PROVIDERS',
    'create_marketplace_clients',
]
