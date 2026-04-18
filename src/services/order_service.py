import asyncio
from loguru import logger
import redis.asyncio as redis

from src.repositories import OrderRepository, UserRepository, ProductRepository
from src.services.cache_service import CacheService
from src.database.models import Order
from src.schemas import OrderResponse, OrderCreate, UserUpdatePatch, ProductUpdate, OrderInDB, OrderItemBase
from src.models.exceptions import InsufficientStockError, BusinessLogicError, NotFoundError, ValidationError


class OrderService:
    def __init__(
            self,
            order_rep: OrderRepository,
            user_rep: UserRepository,
            product_rep: ProductRepository,
            client: redis.Redis):
        self.order_rep = order_rep
        self.user_rep = user_rep
        self.product_rep = product_rep
        self.cache = CacheService(client)

    async def get_all_orders(self, limit: int = 100, offset: int = 0) -> list[Order]:
        async def fetch():

            orders = await self.order_rep.get_all(limit, offset)

            if not orders:
                raise NotFoundError("Заказов нет")

            orders_data = []

            for order in orders:
                orders_data.append({
                    "id": order.id,
                    "user_id": order.user_id,
                    "total": float(order.total),
                    "created_at": order.created_at,
                    "items": [
                        {
                            "id": item.id,
                            "product_id": item.product_id,
                            "quantity": item.quantity,
                            "total": float(item.total)
                        }
                        for item in order.items
                    ]
                })

            return orders_data

        return await self.cache.get_or_set_cache(f"orders:{limit}:{offset}", fetch)

    async def get_order_by_id(self, order_id: int) -> Order:
        async def fetch():
            order = await self.order_rep.get_by_id(order_id)

            if not order:
                logger.warning(f"Order id={order_id} not found")
                raise NotFoundError("Заказ не найден")

            return OrderResponse.model_validate(order).model_dump(mode="json")

        return await self.cache.get_or_set_cache(f"order:{order_id}", fetch)

    async def create_order(self, order: OrderCreate):
        quantity = []
        product_ids = []

        for item in order.items:
            item_quantity = item.quantity
            if item_quantity <= 0:
                logger.warning("create order: quantity must be positive.")
                raise ValidationError("Количество должно быть положительным")

            quantity.append(item_quantity)
            product_ids.append(item.product_id)

        user_id = order.user_id

        async with self.order_rep.db.begin():

            user_db = await self.user_rep.get_by_id_for_update(user_id)

            if not user_db:
                logger.warning(f"User id={user_id} not found")
                raise NotFoundError("Пользователь не найден")


            result = await self.product_rep.get_by_ids_for_update(product_ids)
            products_db = {p.id: p for p in result}

            order_items_db = []
            total = 0

            for idx, product_id in enumerate(product_ids):
                product_db = products_db.get(product_id)

                if not product_db:
                    logger.warning(f"Product id={product_id} not found")
                    raise NotFoundError("Товар не найден")

                if product_db.quantity < quantity[idx]:
                    raise InsufficientStockError("Недостаточно товара на складе")

                product_db.quantity -= quantity[idx]

                product_total = product_db.price * quantity[idx]

                total += product_total

                order_items_db.append((product_db.id, quantity[idx], product_total))

            if user_db.balance < total:
                raise BusinessLogicError("Недостаточно средств на балансе пользователя")

            user_db.balance -= total

            order_data = OrderInDB(user_id=user_id, items=[], total=total).model_dump(exclude_unset=True)

            order_db_id = await self.order_rep.create(order_data)

            for item in order_items_db:
                data = OrderItemBase(order_id=order_db_id, **item).model_dump(exclude_unset=True)
                await self.order_rep.create_order_item(data)

        task_1 = self.cache.delete_products(product_ids)
        task_2 = self.cache.delete_users(order.user_id)
        task_3 = self.cache.delete_orders(order.user_id)

        await asyncio.gather(task_1, task_2, task_3)

        return {
            "order_id": order_db_id,
            "user_id": user_id,
            "products_id": product_ids,
            "quantity": quantity,
            "total": float(total),
        }

    async def delete_order(self, order_id):
        async with self.order_rep.db.begin():
            order = await self.order_rep.get_by_id_for_update(order_id)

            if not order:
                logger.warning(f"Order id={order_id} not found")
                raise NotFoundError("Заказ не найден")

            user_db = await self.user_rep.get_by_id_for_update(order.user_id)
            new_user_data = UserUpdatePatch(balance=user_db.balance + order.total).model_dump(exclude_unset=True)

            await self.user_rep.update(user_db, new_user_data)

            items = await self.order_rep.get_order_products(order_id)

            product_ids = [item.product_id for item in items]
            products = await self.product_rep.get_by_ids(product_ids)

            products_db = {p.id: p for p in products}

            for item in items:
                product_db = products_db[item.product_id]
                data = ProductUpdate(quantity=product_db.quantity + item.quantity).model_dump(exclude_unset=True)
                await self.product_rep.update(product_db, data)

            await self.order_rep.delete(order)

        task_1 = self.cache.delete_products(product_ids)
        task_2 = self.cache.delete_users(order.user_id)
        task_3 = self.cache.delete_orders(order.user_id)

        await asyncio.gather(task_1, task_2, task_3)

        return {"id": order_id, "message": "Заказ удален"}


# Архитектура системы с брокером сообщений для проекта SFMShop:
#
# 1. Producer (src/api/main.py):
#    - При создании заказа (create_order) отправляет сообщения в брокер (RabbitMQ/Kafka)
#    - Формирует события order_created
#    - Передает данные: user_id, order_id, items, total
#
# 2. Очередь сообщений (Broker):
#    - RabbitMQ / Kafka
#    - Хранит задачи до обработки
#    - Гарантирует доставку (ack/nack, durable queues)
#    - Поддерживает retry и DLQ
#
# 3. Consumer (src/services/queue_consumer.py):
#    - Подписывается на события (order_created)
#    - Обрабатывает задачи асинхронно
#
#    Основные задачи:
#    - Отправка email уведомлений пользователю
#    - Обновление аналитики / отчетов
#    - Интеграция с payment-service
#    - Логирование событий
#
# 4. Примеры задач в очереди:
#    - send_email(user_id, order_id)
#    - update_sales_report(order_id, total)
#    - notify_payment_service(order_id)
#
# 5. Надежность:
#    - retry с exponential backoff
#    - DLQ для неуспешных сообщений
#    - подтверждение обработки (ack)
#
# 6. Преимущества:
#    - разгрузка API (не блокирует запрос)
#    - масштабируемость (несколько consumers)
#    - отказоустойчивость (задачи не теряются)

