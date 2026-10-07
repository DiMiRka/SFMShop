import asyncio
import aio_pika
import json
from typing import Any
from loguru import logger

from src.repositories.event_repository import EventRepository
from src.services.cache_service import CacheService
from src.services.event_log_service import build_event


ALL_EVENTS = (
    ("user_exchange", "user.created"),
    ("user_exchange", "user.updated"),
    ("user_exchange", "user.deleted"),
    ("product_exchange", "product.created"),
    ("product_exchange", "product.updated"),
    ("product_exchange", "product.deleted"),
    ("order_exchange", "order.created"),
    ("order_exchange", "order.deleted"),
)


class QueueConsumer:
    def __init__(self, cache: CacheService, url: str, events: EventRepository | None = None):
        self.url = url
        self.cache = cache
        self.events = events
        self.max_retries = 3

        self.connection: Any = None
        self.channel: Any = None

        self.user_exchange: Any = None
        self.order_exchange: Any = None
        self.product_exchange: Any = None

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
            if self.events is not None:
                await self._setup_event_log_consumer()

        except Exception as e:
            logger.error(f"Ошибка подключения к RabbitMQ: {e}")

    @staticmethod
    def get_retry_count(message: aio_pika.IncomingMessage) -> int:
        headers = message.headers or {}
        deaths = headers.get("x-death", [])

        if not isinstance(deaths, list) or not deaths:
            return 0

        first_death = deaths[0]
        if not isinstance(first_death, dict):
            return 0

        count = first_death.get("count", 0)
        return count if isinstance(count, int) else 0

    async def move_to_error_queue(self, message, queue_name):
        await self.channel.default_exchange.publish(
            aio_pika.Message(
                body=message.body,
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                message_id=getattr(message, "message_id", None),
                timestamp=getattr(message, "timestamp", None),
                headers={"x-original-routing-key": getattr(message, "routing_key", None)},
            ),
            routing_key=f"{queue_name}.error"
        )

    async def _declare_queue_with_retry(self, name: str):
        await self.channel.declare_queue(f"{name}.error", durable=True)

        queue = await self.channel.declare_queue(
            name,
            durable=True,
            arguments={
                "x-dead-letter-exchange": "",
                "x-dead-letter-routing-key": f"{name}.retry",
            }
        )

        await self.channel.declare_queue(
            f"{name}.retry",
            durable=True,
            arguments={
                "x-message-ttl": 5000,
                "x-dead-letter-exchange": "",
                "x-dead-letter-routing-key": name
            }
        )

        return queue

    async def _retry_or_park(self, message: aio_pika.IncomingMessage, queue_name: str):
        retry_count = self.get_retry_count(message)

        if retry_count >= self.max_retries:
            await self.move_to_error_queue(message, queue_name)
            logger.error(f"[{queue_name}] отправлено в error после {retry_count} попыток")
        else:
            await message.reject(requeue=False)
            logger.warning(f"[{queue_name}] повтор {retry_count + 1}")

    def _exchange(self, name: str):
        return {
            "user_exchange": self.user_exchange,
            "product_exchange": self.product_exchange,
            "order_exchange": self.order_exchange,
        }[name]

    async def _setup_cache_consumer(self):
        queue = await self._declare_queue_with_retry("cache_queue")

        for exchange, routing_key in ALL_EVENTS:
            await queue.bind(self._exchange(exchange), routing_key)

        await queue.consume(self.process_cache_event)

    async def process_cache_event(self, message: aio_pika.IncomingMessage):
        async with message.process(requeue=False, ignore_processed=True):
            try:
                data = json.loads(message.body)
                routing_key = message.routing_key or ""

                logger.info(f"[CACHE] {routing_key} -> {data}")

                if routing_key.startswith("order.") or routing_key == "user.deleted":
                    await asyncio.gather(
                        self.invalidate_order_cache(data),
                        self.invalidate_product_cache(data),
                        self.invalidate_user_cache(data),
                    )

                elif routing_key.startswith("user."):
                    await self.invalidate_user_cache(data)

                elif routing_key.startswith("product."):
                    await self.invalidate_product_cache(data)
            except Exception:
                await self._retry_or_park(message, "cache_queue")

    async def invalidate_user_cache(self, data: dict):
        user_ids = data.get("user_ids", None)
        logger.info("Инвалидация кэша после изменения пользователей")
        await self.cache.delete_users(user_ids)

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
        queue = await self._declare_queue_with_retry("notification_queue")

        await queue.bind(self.order_exchange, "order.created")

        await queue.consume(self.process_notification)

    async def process_notification(self, message: aio_pika.IncomingMessage):
        async with message.process(requeue=False, ignore_processed=True):
            try:
                data = json.loads(message.body)
                logger.info(f"Отправка email для заказа {data.get('order_ids')}")
            except Exception:
                await self._retry_or_park(message, "notification_queue")

    async def _setup_event_log_consumer(self):
        queue = await self._declare_queue_with_retry("event_log_queue")

        for exchange, routing_key in ALL_EVENTS:
            await queue.bind(self._exchange(exchange), routing_key)

        await queue.consume(self.process_event_log)

    async def process_event_log(self, message: aio_pika.IncomingMessage):
        if self.events is None:
            return

        async with message.process(requeue=False, ignore_processed=True):
            try:
                event = build_event(
                    routing_key=message.routing_key or "",
                    payload=json.loads(message.body),
                    message_id=message.message_id,
                    occurred_at=message.timestamp,
                )
                await self.events.add(event)
            except Exception:
                await self._retry_or_park(message, "event_log_queue")

    async def start(self):
        await self._connect()
        logger.info("Consumer started")
