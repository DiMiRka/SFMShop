import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from loguru import logger

from src.api.main import sfmshop_app as app
from src.core import dependencies
from src.services.health_service import HealthService


client = TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


class Connection:
    def __init__(self, engine):
        self.engine = engine

    async def __aenter__(self):
        if self.engine.error:
            raise self.engine.error
        return self

    async def __aexit__(self, *args):
        return False

    async def execute(self, statement):
        self.engine.statements.append(str(statement))


class Engine:
    def __init__(self, error=None):
        self.error = error
        self.statements = []

    def connect(self):
        return Connection(self)


def make_service(primary=None, replica=None, redis_ping=None, queue_closed=False, timeout=1.0):
    redis = SimpleNamespace(ping=redis_ping or AsyncMock(return_value=True))
    queue = SimpleNamespace(connection=SimpleNamespace(is_closed=queue_closed))
    engines = {"postgres": primary or Engine(), "postgres_replica": replica or Engine()}
    return HealthService(engines, redis, queue, timeout=timeout)


@pytest.mark.anyio
async def test_ready_when_all_dependencies_respond():
    primary = Engine()

    result = await make_service(primary=primary).readiness()

    assert result == {
        "status": "ok",
        "checks": {"postgres": "ok", "postgres_replica": "ok", "redis": "ok", "rabbitmq": "ok"},
    }
    assert primary.statements == ["SELECT 1"]


@pytest.mark.anyio
@pytest.mark.parametrize("kwargs, failed", [
    ({"primary": Engine(ConnectionError("db down"))}, "postgres"),
    ({"replica": Engine(ConnectionError("replica down"))}, "postgres_replica"),
])
async def test_critical_dependency_failure_makes_app_not_ready(kwargs, failed, log_messages):
    result = await make_service(**kwargs).readiness()

    assert result["status"] == "fail"
    assert result["checks"][failed] == "fail"
    assert "health_check_failed" in log_messages


@pytest.mark.anyio
@pytest.mark.parametrize("kwargs, failed", [
    ({"queue_closed": True}, "rabbitmq"),
    ({"redis_ping": AsyncMock(side_effect=ConnectionError("redis down"))}, "redis"),
])
async def test_cache_and_queue_failures_only_degrade_readiness(kwargs, failed):
    result = await make_service(**kwargs).readiness()

    assert result["status"] == "degraded"
    assert result["checks"][failed] == "fail"


@pytest.mark.anyio
async def test_hanging_check_fails_by_timeout():
    async def hang():
        await asyncio.sleep(10)

    started = asyncio.get_running_loop().time()
    result = await make_service(redis_ping=hang, timeout=0.05).readiness()

    assert result["checks"]["redis"] == "fail"
    assert asyncio.get_running_loop().time() - started < 1


def use_health(status):
    service = SimpleNamespace(readiness=AsyncMock(return_value={"status": status, "checks": {}}))
    app.dependency_overrides[dependencies.get_health_service] = lambda: service


@pytest.mark.parametrize("status, code", [("ok", 200), ("degraded", 200), ("fail", 503)])
def test_ready_endpoint_maps_status_to_http_code(status, code):
    use_health(status)

    response = client.get("/health/ready")

    assert response.status_code == code
    assert response.json()["status"] == status


def test_live_endpoint_needs_no_dependencies_or_token():
    assert client.get("/health/live").json() == {"status": "ok"}


def test_successful_probes_do_not_flood_info_logs():
    use_health("ok")
    records = []
    handler_id = logger.add(lambda message: records.append(message.record), level="INFO")
    try:
        client.get("/health/live")
        client.get("/health/ready")
    finally:
        logger.remove(handler_id)

    assert not [r for r in records if r["extra"].get("path", "").startswith("/health")]
