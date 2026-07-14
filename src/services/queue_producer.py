import aio_pika
import asyncio
import json
from loguru import logger

from src.core.config import app_settings


class QueueProducer:
    _instance = None
    _lock = asyncio.Lock()

    def __init__(
            self,
            url: str,
            max_retries: int | None = None,
            base_delay: float | None = None,
            backoff_multiplier: float | None = None):
        self.url = url
        self.max_retries = max_retries if max_retries is not None else app_settings.rabbitmq_max_retries
        self.base_delay = base_delay if base_delay is not None else app_settings.rabbitmq_base_delay
        self.backoff_multiplier = (backoff_multiplier if backoff_multiplier is not None
                                   else app_settings.rabbitmq_backoff_multiplier)

        self.connection: aio_pika.RobustConnection | None = None
        self.channel: aio_pika.abc.AbstractChannel | None = None

        self.exchanges: dict[str, aio_pika.abc.AbstractExchange] = {}

    @classmethod
    async def get_instance(
            cls,
            url: str,
            max_retries: int | None = None,
            base_delay: float | None = None,
            backoff_multiplier: float | None = None):
        async with cls._lock:
            if cls._instance is None:
                instance = cls(
                    url,
                    max_retries=max_retries,
                    base_delay=base_delay,
                    backoff_multiplier=backoff_multiplier,
                )
                await instance._connect()
                cls._instance = instance
            return cls._instance

    async def _connect(self):
        try:
            self.connection = await aio_pika.connect_robust(url=self.url)
            self.channel = await self.connection.channel()

            for name in ["user_exchange", "order_exchange", "product_exchange"]:
                self.exchanges[name] = await self.channel.declare_exchange(
                    name,
                    aio_pika.ExchangeType.DIRECT,
                    durable=True
                )

            logger.info("rabbitmq_connected")

        except Exception as e:
            logger.error(f"rabbitmq_connect_error error={e}")
            return False

    async def _ensure_connection(self):
        if self.connection is None or self.connection.is_closed:
            logger.warning("rabbitmq_reconnecting")
            await self._connect()

    async def publish_event(self, exchange: str, routing_key: str, message: dict):
        await self._ensure_connection()

        if exchange not in self.exchanges:
            raise ValueError(f"Exchange {exchange} not found")

        for attempt in range(self.max_retries):
            try:
                await self.exchanges[exchange].publish(
                    aio_pika.Message(
                        body=json.dumps(message).encode(),
                        delivery_mode=aio_pika.DeliveryMode.PERSISTENT
                    ),
                    routing_key=routing_key
                )
                logger.info(f"event_published exchange={exchange} routing_key={routing_key} message={message}")

                return True

            except Exception as e:
                logger.error(f"event_publish_error error={e}")

                if attempt == self.max_retries - 1:
                    raise

                delay = self.base_delay * (self.backoff_multiplier ** attempt)
                logger.warning(f"rabbitmq_publish_retry retry_in={delay} attempt={attempt + 1}/{self.max_retries}")

                await asyncio.sleep(delay)
                await self._connect()

    async def close(self):
        if self.connection and not self.connection.is_closed:
            await self.connection.close()