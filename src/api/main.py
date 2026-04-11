from fastapi import FastAPI
import uvicorn
from loguru import logger

from src.api.v1 import v1_router
from src.services.log_service import setup_logging

setup_logging()
app = FastAPI(
    title="SFMShop API",
    description="API для интернет магазина SFMShop",
    version="1.0.0"
)

app.include_router(v1_router)


if __name__ == "__main__":
    setup_logging()
    logger.info("Сервер запущен")
    uvicorn.run("src.api.main:app", reload=True, log_level="critical")

# Структура REST API для проекта SFMShop:
#
# Товары (/products):
# - GET /products - получить список товаров (200 OK)
# - GET /products/{product_id} - получить товар по ID (200 OK или 404 Not Found)
# - POST /products - создать товар (201 Created или 400 Bad Request)
# - PUT /products/{product_id} - полностью обновить товар (200 OK или 404 Not Found)
# - DELETE /products/{product_id} - удалить товар (204 No Content или 404 Not Found)
#
# Пользователи (/users):
# - GET /users - получить список пользователей (200 OK)
# - GET /users/{user_id} - получить пользователя по ID (200 OK или 404 Not Found)
# - POST /users - создать пользователя (201 Created или 400 Bad Request)
# - PUT /users/{user_id} - полностью обновить пользователя (200 OK или 404 Not Found)
# - DELETE /users/{user_id} - удалить пользователя (204 No Content или 404 Not Found)
#
# Заказы (/orders):
# - GET /orders - получить список заказов (200 OK)
# - GET /orders/{order_id} - получить заказ по ID (200 OK или 404 Not Found)
# - POST /orders - создать заказ (201 Created или 400 Bad Request)
# - DELETE /orders?order_id={id} - удалить заказ (204 No Content или 404 Not Found)
#
# Вложенные ресурсы:
# - GET /users/{user_id}/orders - получить заказы пользователя (200 OK или 404 Not Found)
#
# Пагинация:
# - GET /products?limit=100&offset=0 - получить товары с пагинацией
# - GET /orders?limit=100&offset=0 - получить заказы с пагинацией
