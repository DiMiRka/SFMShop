import asyncio
from fastapi import FastAPI
from sqlalchemy import select
import httpx

from src.database.connection import read_db_dependency, redis_client
from src.services.cache_service import CacheService
from src.database.models import Product

app = FastAPI()

cache = CacheService(redis_client)


@app.get("/api/products/{product_id}/full")
async def get_product_full(db: read_db_dependency, product_id: int):

    async def fetch():
        async with httpx.AsyncClient(timeout=5.0) as client:
            for attempt in range(3):
                try:
                    response = await client.get("https://api.sfmshop.ru/reviews/product/2")
                    response.raise_for_status()
                    return response.json()

                except httpx.TimeoutException:
                    print(f"Таймаут (попытка {attempt + 1}/{3})")

                except httpx.HTTPStatusError as e:
                    if e.response.status_code >= 500:
                        print(f"Ошибка сервера {e.response.status_code} (попытка {attempt + 1})")
                    else:
                        print(f"Ошибка клиента: {e.response.status_code}")
                        return None

                except httpx.ConnectError:
                    print(f"Нет соединения (попытка {attempt + 1}/{3})")

    product_task = db.execute(select(Product).where(Product.id == product_id))

    views_task = cache.get_count(f"count_views:{product_id}")

    reviews_task = cache.get_or_set_cache(f"reviews:{product_id}", fetch, ttl=600)

    result, views, reviews = await asyncio.gather(
        product_task,
        views_task,
        reviews_task
    )

    product = result.scalar_one_or_none()

    if not product:
        return {"error": "Товар не найден"}

    return {
        **product,
        "price": float(product.price),
        "reviews": reviews,
        "views": views,
    }
