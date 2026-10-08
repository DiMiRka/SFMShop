from decimal import Decimal
from loguru import logger

from src.repositories.product_repository import ProductRepository
from src.services.cache_service import CacheService
from src.services.queue_producer import QueueProducer
from src.schemas import ProductResponse, ProductCreate, ProductUpdate, ProductDetailResponse
from src.models.exceptions import NotFoundError


class ProductService:
    def __init__(
            self,
            product_rep: ProductRepository,
            cache: CacheService,
            queue: QueueProducer):
        self.product_rep = product_rep
        self.cache = cache
        self.queue = queue

    async def get_all_products(self, limit: int, offset: int):
        async def fetch():
            products = await self.product_rep.get_all(limit=limit, offset=offset)
            total = await self.product_rep.get_count_all()

            products_data = [
                ProductResponse.model_validate(product).model_dump(mode="json")
                for product in products
            ]

            response = {
                "total": total,
                "limit": limit,
                "offset": offset,
                "products": products_data,
            }

            return response

        return await self.cache.get_or_set_cache(f"products:{limit}:{offset}", fetch)

    async def get_product_by_id(self, product_id: int):
        async def fetch():
            product = await self.product_rep.get_by_id(product_id)

            if not product:
                logger.warning(f"Product id={product_id} not found")
                raise NotFoundError("Товар не найден")

            average_rating, reviews_count = await self.product_rep.get_rating(product_id)
            card = ProductDetailResponse.model_validate(product)
            card.average_rating, card.reviews_count = average_rating, reviews_count
            return card.model_dump(mode="json")

        return await self.cache.get_or_set_cache(f"product:{product_id}", fetch)

    async def search_products(
            self,
            name_query: str | None = None,
            min_price: Decimal | None = None,
            max_price: Decimal | None = None,
            in_stock: bool = False,
            limit: int = 10) -> list[dict]:
        products = await self.product_rep.search(
            name_query=name_query,
            min_price=min_price,
            max_price=max_price,
            in_stock=in_stock,
            limit=limit,
        )
        return [ProductResponse.model_validate(product).model_dump(mode="json") for product in products]

    async def create_product(self, product: ProductCreate):
        data = product.model_dump(mode="json")

        async with self.product_rep.db.begin():
            product_id = await self.product_rep.create(data)

        await self.queue.publish_event(
            "product_exchange",
            "product.created",
            {"product_ids": product_id}
        )

        return {"id": product_id, "message": "Товар добавлен"}

    async def update_product(self, product_id: int, product_update: ProductUpdate):
        async with self.product_rep.db.begin():
            product_db = await self.product_rep.get_by_id(product_id)

            if not product_db:
                logger.warning(f"Product id={product_id} not found")
                raise NotFoundError("Товар не найден")

            data = product_update.model_dump(exclude_unset=True)

            await self.product_rep.update(product_db, data)

        await self.queue.publish_event(
            "product_exchange",
            "product.updated",
            {"product_ids": product_id}
        )

        return {"id": product_id, "message": "Товар обновлен"}

    async def delete_product(self, product_id: int):
        async with self.product_rep.db.begin():
            product_db = await self.product_rep.get_by_id(product_id)

            if not product_db:
                logger.warning(f"Product id={product_id} not found")
                raise NotFoundError("Товар не найден")

            await self.product_rep.delete(product_db)

        await self.queue.publish_event(
            "product_exchange",
            "product.deleted",
            {"product_ids": product_id}
        )

        return {"id": product_id, "message": "Товар удален"}
