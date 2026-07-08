import aio_pika
import asyncio
import json
from loguru import logger


class QueueProducer:
    _instance = None
    _lock = asyncio.Lock()

    def __init__(self, url: str):
        self.url = url
        self.max_retries: int = 3
        self.base_delay = 0.5

        self.connection: aio_pika.RobustConnection | None = None
        self.channel: aio_pika.abc.AbstractChannel | None = None

        self.exchanges: dict[str, aio_pika.abc.AbstractExchange] = {}

    @classmethod
    async def get_instance(cls, url: str):
        async with cls._lock:
            if cls._instance is None:
                instance = cls(url)
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

            logger.info("RabbitMQ connected")

        except Exception as e:
            logger.error(f"Ошибка подключения к RabbitMQ: {e}")
            return False

    async def _ensure_connection(self):
        if self.connection is None or self.connection.is_closed:
            logger.warning("Reconnecting to RabbitMQ...")
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
                logger.info(f"[EVENT] {exchange}:{routing_key} -> {message}")

                return True

            except Exception as e:
                logger.error(f"Ошибка отправки задачи: {e}")

                if attempt == self.max_retries - 1:
                    raise

                delay = self.base_delay * (2 ** attempt)
                logger.warning(f"Retry in {delay}s... ({attempt+1}/{self.max_retries})")

                await asyncio.sleep(delay)
                await self._connect()

    async def close(self):
        if self.connection and not self.connection.is_closed:
            await self.connection.close()
