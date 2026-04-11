from fastapi import APIRouter

from src.api.v1.orders import orders_router
from src.api.v1.products import products_router
from src.api.v1.users import users_router

v1_router = APIRouter(prefix="/v1")

v1_router.include_router(orders_router)
v1_router.include_router(products_router)
v1_router.include_router(users_router)
