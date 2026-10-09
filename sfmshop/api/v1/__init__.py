from fastapi import APIRouter

from sfmshop.api.v1.orders import orders_router
from sfmshop.api.v1.products import products_router
from sfmshop.api.v1.users import users_router
from sfmshop.api.v1.auth import auth_router
from sfmshop.api.v1.assistant import assistant_router
from sfmshop.api.v1.events import events_router
from sfmshop.api.v1.reviews import reviews_router

v1_router = APIRouter(prefix="/v1")

v1_router.include_router(orders_router)
v1_router.include_router(products_router)
v1_router.include_router(users_router)
v1_router.include_router(auth_router)
v1_router.include_router(assistant_router)
v1_router.include_router(events_router)
v1_router.include_router(reviews_router)
