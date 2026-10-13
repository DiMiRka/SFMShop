from typing import Annotated

from fastapi import APIRouter, Query, status, Response

from sfmshop.core.actor import Actor
from sfmshop.schemas import ProductCreate, ProductUpdate
from sfmshop.core.dependencies import admin_user, product_write_service, product_read_service


products_router = APIRouter(prefix="/products", tags=['products'])


@products_router.get("/", summary="Получить товары или найти по названию", status_code=status.HTTP_200_OK)
async def get_products(service: product_read_service, response: Response,
                       limit: int = 100, offset: int = 0,
                       q: Annotated[str | None, Query(min_length=3, max_length=100,
                                                      description="Поиск по названию, допускает опечатки")] = None):
    if q is not None:
        return await service.search_catalog(q, limit, offset)

    return await service.get_all_products(limit, offset)


@products_router.get("/{product_id}", summary="Получить товар", status_code=status.HTTP_200_OK)
async def get_product(service: product_read_service, product_id: int):
    return await service.get_product_by_id(product_id)


@products_router.post("/", summary="Создать новый товар", status_code=status.HTTP_201_CREATED)
async def post_product(admin: admin_user, service: product_write_service, product: ProductCreate):
    return await service.create_product(product, actor=Actor.of(admin))


@products_router.put("/{product_id}", summary="Обновить товар", status_code=status.HTTP_200_OK)
async def put_product(admin: admin_user, service: product_write_service, product_id: int, product: ProductUpdate):
    return await service.update_product(product_id, product, actor=Actor.of(admin))


@products_router.delete("/{product_id}", summary="Удалить товар", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(admin: admin_user, service: product_write_service, product_id: int):
    return await service.delete_product(product_id, actor=Actor.of(admin))
