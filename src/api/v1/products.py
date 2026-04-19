from fastapi import APIRouter, status, Response

from src.schemas import ProductCreate, ProductUpdate
from src.core.dependencies import current_user, product_write_service, product_read_service


products_router = APIRouter(prefix="/products", tags=['products'])


@products_router.get("/", summary="Получить все товары", status_code=status.HTTP_200_OK)
async def get_products(service: product_read_service, response: Response,
                       limit: int = 100, offset: int = 0):

    return await service.get_all_products(limit, offset)


@products_router.get("/{product_id}", summary="Получить товар", status_code=status.HTTP_200_OK)
async def get_product(service: product_read_service, product_id: int):
    return await service.get_product_by_id(product_id)


@products_router.post("/", summary="Создать новый товар", status_code=status.HTTP_201_CREATED)
async def post_product(cu: current_user, service: product_write_service, product: ProductCreate):
    return await service.create_product(product)


@products_router.put("/{product_id}", summary="Обновить товар", status_code=status.HTTP_200_OK)
async def put_product(cu: current_user, service: product_write_service, product_id: int, product: ProductUpdate):
    return await service.update_product(product_id, product)


@products_router.delete("/{product_id}", summary="Удалить товар", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(cu: current_user, service: product_write_service, product_id: int):
    return await service.delete_product(product_id)
