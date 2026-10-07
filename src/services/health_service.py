import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, cast

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from src.services.log_service import log_service
from src.services.queue_producer import QueueProducer


CHECK_TIMEOUT = 2.0


class HealthService:
    def __init__(
            self,
            engines: dict[str, AsyncEngine],
            redis: Redis,
            queue: QueueProducer,
            timeout: float = CHECK_TIMEOUT):
        self.engines = engines
        self.redis = redis
        self.queue = queue
        self.timeout = timeout

    async def readiness(self) -> dict[str, Any]:
        critical: dict[str, Callable[[], Awaitable[Any]]] = {
            name: self._postgres_check(engine) for name, engine in self.engines.items()
        }
        critical["redis"] = self._redis
        optional: dict[str, Callable[[], Awaitable[Any]]] = {"rabbitmq": self._rabbitmq}

        checks = {**critical, **optional}
        results = await asyncio.gather(*(self._run(name, check) for name, check in checks.items()))
        statuses = dict(zip(checks, results))

        if not all(statuses[name] for name in critical):
            status = "fail"
        elif not all(statuses[name] for name in optional):
            status = "degraded"
        else:
            status = "ok"

        return {"status": status, "checks": {name: "ok" if ok else "fail" for name, ok in statuses.items()}}

    async def _run(self, name: str, check: Callable[[], Awaitable[Any]]) -> bool:
        try:
            await asyncio.wait_for(check(), timeout=self.timeout)
        except Exception as exc:
            log_service.warning("health_check_failed", check=name, error=repr(exc))
            return False
        return True

    @staticmethod
    def _postgres_check(engine: AsyncEngine) -> Callable[[], Awaitable[None]]:
        async def check() -> None:
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))

        return check

    async def _redis(self) -> None:
        await cast(Awaitable[bool], self.redis.ping())

    async def _rabbitmq(self) -> None:
        connection = getattr(self.queue, "connection", None)
        if connection is None or connection.is_closed:
            raise ConnectionError("RabbitMQ connection is closed")
