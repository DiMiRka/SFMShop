import socket
import urllib.request
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

from src.api.main import sfmshop_app as app
from src.clients.llm import LLMResult, ToolCall
from src.core import dependencies
from src.core.metrics import start_metrics_server
from src.models.exceptions import LLMUnavailableError
from src.schemas import OrderCreate, OrderItemBase
from src.services.cache_service import CacheService
from src.services.order_service import OrderService
from tests.test_assistant_service import ScriptedLLM, call, final, make_service
from tests.test_queue import build_producer
from tests.test_services import FakeCache, FakeQueue, OrderRepoFake, ProductRepoFake, UserRepoFake
from tests.test_unit_core import FlakyRedis, MemoryRedis


client = TestClient(app, raise_server_exceptions=False)


def sample(name, **labels):
    return REGISTRY.get_sample_value(name, labels) or 0


def teardown_function():
    app.dependency_overrides.clear()


def use_product_service(service):
    async def override():
        return service

    app.dependency_overrides[dependencies.get_product_read_service] = override


def test_http_metrics_use_route_template_not_raw_path():
    service = MagicMock()
    service.get_product_by_id = AsyncMock(return_value={"id": 7})
    use_product_service(service)
    labels = {"method": "GET", "route": "/v1/products/{product_id}"}
    before = sample("sfmshop_http_requests_total", status="200", **labels)
    before_duration = sample("sfmshop_http_request_duration_seconds_count", **labels)

    client.get("/v1/products/7")
    client.get("/v1/products/8")

    assert sample("sfmshop_http_requests_total", status="200", **labels) == before + 2
    assert sample("sfmshop_http_request_duration_seconds_count", **labels) == before_duration + 2
    assert sample("sfmshop_http_requests_total", method="GET", route="/v1/products/7", status="200") == 0


def test_unknown_paths_share_one_label_and_probes_are_not_counted():
    unmatched = {"method": "GET", "route": "unmatched", "status": "404"}
    before = sample("sfmshop_http_requests_total", **unmatched)

    client.get("/v1/no-such-thing/1")
    client.get("/random/path/42")
    client.get("/health/live")

    assert sample("sfmshop_http_requests_total", **unmatched) == before + 2
    assert sample("sfmshop_http_requests_total", method="GET", route="/health/live", status="200") == 0


def test_unhandled_error_is_counted_as_500():
    service = MagicMock()
    service.get_product_by_id = AsyncMock(side_effect=RuntimeError("db is down"))
    use_product_service(service)
    labels = {"method": "GET", "route": "/v1/products/{product_id}", "status": "500"}
    before = sample("sfmshop_http_requests_total", **labels)

    assert client.get("/v1/products/1").status_code == 500

    assert sample("sfmshop_http_requests_total", **labels) == before + 1


@pytest.mark.anyio
async def test_cache_results_are_counted():
    before = {r: sample("sfmshop_cache_requests_total", result=r) for r in ("hit", "miss", "error", "skipped")}

    async def fetch():
        return {"ok": True}

    cache = CacheService(MemoryRedis())
    await cache.get_or_set_cache("key", fetch)
    await cache.get_or_set_cache("key", fetch)

    broken = CacheService(FlakyRedis(fail_get=True), retry_after=60)
    await broken.get_or_set_cache("key", fetch)
    await broken.get_or_set_cache("key", fetch)

    after = {r: sample("sfmshop_cache_requests_total", result=r) for r in before}
    assert {r: after[r] - before[r] for r in before} == {"hit": 1, "miss": 1, "error": 1, "skipped": 1}


@pytest.mark.anyio
async def test_event_publishing_success_and_failure_are_counted(monkeypatch):
    ok = {"routing_key": "order.created", "result": "ok"}
    failed = {"routing_key": "order.created", "result": "failed"}
    before_ok, before_failed = sample("sfmshop_events_published_total", **ok), sample(
        "sfmshop_events_published_total", **failed)

    producer, _ = build_producer(monkeypatch, None)
    await producer.publish_event("order_exchange", "order.created", {"order_ids": 1})
    producer, _ = build_producer(monkeypatch, ConnectionError("down"))
    await producer.publish_event("order_exchange", "order.created", {"order_ids": 1})

    assert sample("sfmshop_events_published_total", **ok) == before_ok + 1
    assert sample("sfmshop_events_published_total", **failed) == before_failed + 1


@pytest.mark.anyio
async def test_created_orders_are_counted():
    before = sample("sfmshop_orders_created_total")
    service = OrderService(OrderRepoFake(), UserRepoFake(), ProductRepoFake(), FakeCache(), FakeQueue())

    await service.create_order(1, OrderCreate(items=[OrderItemBase(product_id=1, quantity=1)]))

    assert sample("sfmshop_orders_created_total") == before + 1


class UnavailableLLM:
    async def complete(self, *args):
        raise LLMUnavailableError("down")


@pytest.mark.anyio
async def test_assistant_outcomes_and_tool_calls_are_counted():
    outcomes = ("answered", "refusal", "steps_exceeded", "unavailable")
    before = {o: sample("sfmshop_assistant_requests_total", outcome=o) for o in outcomes}
    tool_labels = [("get_product", "ok"), ("get_product", "not_found"), ("get_product", "invalid_arguments"),
                   ("unknown", "unknown_tool")]
    tools_before = {t: sample("sfmshop_assistant_tool_calls_total", tool=t[0], result=t[1]) for t in tool_labels}

    await make_service(ScriptedLLM([
        LLMResult(stop_reason="tool_use", tool_calls=[
            ToolCall("t1", "get_product", {"product_id": 1}),
            ToolCall("t2", "get_product", {"product_id": 999}),
            ToolCall("t3", "get_product", {"product_id": "abc"}),
            ToolCall("t4", "drop_database_please", {}),
        ]),
        final("ok", product_ids=[1]),
    ])).ask("x")
    await make_service(ScriptedLLM([LLMResult(stop_reason="refusal")])).ask("x")
    await make_service(ScriptedLLM([call("get_product", {"product_id": 1})]), max_steps=1).ask("x")
    with pytest.raises(LLMUnavailableError):
        await make_service(UnavailableLLM()).ask("x")

    assert {o: sample("sfmshop_assistant_requests_total", outcome=o) - before[o] for o in outcomes} == {
        "answered": 1, "refusal": 1, "steps_exceeded": 1, "unavailable": 1,
    }
    assert {t: sample("sfmshop_assistant_tool_calls_total", tool=t[0], result=t[1]) - tools_before[t]
            for t in tool_labels} == {("get_product", "ok"): 2, ("get_product", "not_found"): 1,
                                      ("get_product", "invalid_arguments"): 1, ("unknown", "unknown_tool"): 1}
    assert sample("sfmshop_assistant_tool_calls_total", tool="drop_database_please", result="unknown_tool") == 0


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_metrics_server_serves_metrics_on_separate_port():
    port = free_port()

    assert start_metrics_server(None) is False
    assert start_metrics_server(port) is True
    body = urllib.request.urlopen(f"http://127.0.0.1:{port}/metrics", timeout=5).read().decode()
    assert "sfmshop_http_requests_total" in body


def test_busy_metrics_port_does_not_stop_the_app(monkeypatch, log_messages):
    from src.core import metrics

    def port_in_use(port):
        raise OSError("address already in use")

    monkeypatch.setattr(metrics, "start_http_server", port_in_use)

    assert start_metrics_server(9100) is False
    assert "metrics_server_not_started" in log_messages


def test_metrics_are_not_exposed_on_public_app_port():
    assert client.get("/metrics").status_code == 404


@pytest.mark.parametrize("config", [
    "deploy/prometheus/alerts.yml",
    "deploy/grafana/dashboards/sfmshop-service.json",
])
def test_alerts_and_dashboard_reference_only_exported_metrics(config):
    import re
    from pathlib import Path

    from prometheus_client import Counter, Histogram

    from src.core import metrics

    exported = set()
    for value in vars(metrics).values():
        if isinstance(value, Counter):
            exported.add(f"{value._name}_total")
        elif isinstance(value, Histogram):
            exported |= {f"{value._name}_bucket", f"{value._name}_count", f"{value._name}_sum"}

    text = (Path(__file__).resolve().parents[1] / config).read_text(encoding="utf-8")
    referenced = set(re.findall(r"sfmshop_[a-z_]+_(?:total|bucket|count|sum)\b", text))

    assert referenced
    assert referenced <= exported, sorted(referenced - exported)
