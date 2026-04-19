from loguru import logger

from src.repositories.product_repository import ProductRepository
from src.services.cache_service import CacheService
from src.services.queue_producer import QueueProducer
from src.schemas import ProductResponse, ProductCreate, ProductUpdate
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

            return ProductResponse.model_validate(product).model_dump(mode="json")

        return await self.cache.get_or_set_cache(f"product:{product_id}", fetch)

    async def create_product(self, product: ProductCreate):
        data = product.model_dump(mode="json")
        product_id = await self.product_rep.create(data)

        await self.queue.publish_event(
            "product_exchange",
            "product.created",
            {}
        )

        return {"id": product_id, "message": "Товар добавлен"}

    async def update_product(self, product_id: int, product_update: ProductUpdate):
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
