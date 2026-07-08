import asyncio
import aio_pika
import json
from loguru import logger

from src.services.cache_service import CacheService


class QueueConsumer:
    def __init__(self, cache: CacheService, url: str):
        self.url = url
        self.cache = cache
        self.max_retries = 3

        self.connection = None
        self.channel = None

        self.user_exchange = None
        self.order_exchange = None
        self.product_exchange = None

    async def _connect(self):
        try:
            self.connection = await aio_pika.connect_robust(url=self.url)
            self.channel = await self.connection.channel()

            await self.channel.set_qos(prefetch_count=10)

            self.user_exchange = await self.channel.declare_exchange(
                "user_exchange", aio_pika.ExchangeType.DIRECT, durable=True
            )
            self.order_exchange = await self.channel.declare_exchange(
                "order_exchange", aio_pika.ExchangeType.DIRECT, durable=True
            )
            self.product_exchange = await self.channel.declare_exchange(
                "product_exchange", aio_pika.ExchangeType.DIRECT, durable=True
            )

            await self._setup_cache_consumer()
            await self._setup_notification_consumer()

        except Exception as e:
            logger.error(f"Ошибка подключения к RabbitMQ: {e}")

    @staticmethod
    def get_retry_count(message: aio_pika.IncomingMessage):
        headers = message.headers or {}
        deaths = headers.get("x-death", [])

        if not deaths:
            return 0

        return deaths[0].get("count", 0)

    async def move_to_error_queue(self, message, queue_name):
        await self.channel.default_exchange.publish(
            aio_pika.Message(
                body=message.body,
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT
            ),
            routing_key=f"{queue_name}.error"
        )

    async def _setup_cache_consumer(self):
        await self.channel.declare_queue("cache_queue.error", durable=True)

        queue = await self.channel.declare_queue(
            "cache_queue",
            durable=True,
            arguments={
                "x-dead-letter-exchange": "",
                "x-dead-letter-routing-key": "cache_queue.retry",
            }
        )

        await self.channel.declare_queue(
            "cache_queue.retry",
            durable=True,
            arguments={
                "x-message-ttl": 5000,
                "x-dead-letter-exchange": "",
                "x-dead-letter-routing-key": "cache_queue"
            }
        )

        bindings = [
            (self.user_exchange, "user.created"),
            (self.user_exchange, "user.updated"),
            (self.user_exchange, "user.deleted"),
            (self.product_exchange, "product.created"),
            (self.product_exchange, "product.updated"),
            (self.product_exchange, "product.deleted"),
            (self.order_exchange, "order.created"),
            (self.order_exchange, "order.deleted"),
        ]

        for exchange, routing_key in bindings:
            await queue.bind(exchange, routing_key)

        await queue.consume(self.process_cache_event)

    async def process_cache_event(self, message: aio_pika.IncomingMessage):
        async with message.process(requeue=False):
            try:
                data = json.loads(message.body)
                routing_key = message.routing_key

                logger.info(f"[CACHE] {routing_key} -> {data}")

                if routing_key.startswith("user."):
                    await self.invalidate_user_cache(data)

                elif routing_key.startswith("product."):
                    await self.invalidate_product_cache(data)

                elif routing_key.startswith("order.") or routing_key == "user.deleted":
                    await asyncio.gather(
                        self.invalidate_order_cache(data),
                        self.invalidate_product_cache(data),
                        self.invalidate_user_cache(data),
                    )
            except Exception:
                retry_count = self.get_retry_count(message)

                if retry_count >= self.max_retries:
                    await self.move_to_error_queue(message, "cache_queue")
                    logger.error(f"[CACHE] отправлено в error после {retry_count} попыток")
                else:
                    await message.reject(requeue=False)
                    logger.warning(f"[CACHE] повтор {retry_count + 1}")

    async def invalidate_user_cache(self, data: dict):
        user_id = data.get("user_id", None)
        logger.info(f"Инвалидация кэша после изменения пользователей")
        await self.cache.delete_users(user_id)

    async def invalidate_product_cache(self, data: dict):
        product_ids = data.get("product_ids", None)
        logger.info("Инвалидация кэша после изменения товаров")
        await self.cache.delete_products(product_ids)

    async def invalidate_order_cache(self, data: dict):
        user_ids = data.get("user_ids", None)
        order_ids = data.get("order_ids", None)
        logger.debug("Инвалидация кэша после изменения заказов")
        await self.cache.delete_orders(user_ids, order_ids)

    async def _setup_notification_consumer(self):
        await self.channel.declare_queue("notification_queue.error", durable=True)

        queue = await self.channel.declare_queue(
            "notification_queue",
            durable=True,
            arguments={
                "x-dead-letter-exchange": "",
                "x-dead-letter-routing-key": "notification_queue.retry"
            }
        )

        await self.channel.declare_queue(
            "notification_queue.retry",
            durable=True,
            arguments={
                "x-message-ttl": 5000,
                "x-dead-letter-exchange": "",
                "x-dead-letter-routing-key": "notification_queue"
            }
        )

        await queue.bind(self.order_exchange, "order.created")

        await queue.consume(self.process_notification)

    async def process_notification(self, message: aio_pika.IncomingMessage):
        async with message.process(requeue=False):
            try:
                data = json.loads(message.body)
                logger.info(f"Отправка email для заказа {data.get('order_id')}")
            except Exception as e:
                retry_count = self.get_retry_count(message)

                if retry_count >= self.max_retries:
                    await self.move_to_error_queue(message, "notification_queue")
                    logger.error(f"[EMAIL] moved to error after {retry_count}")
                else:
                    await message.reject(requeue=False)

    async def start(self):
        await self._connect()
        logger.info("Consumer started")
