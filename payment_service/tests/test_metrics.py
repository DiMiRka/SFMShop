import re
import socket
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from prometheus_client import REGISTRY, Counter, Histogram

from payment.core import metrics
from payment.core.metrics import start_metrics_server
from payment.main import app
from payment.schemas import ChargeRequest


REPO_ROOT = Path(__file__).resolve().parents[2]


def sample(name, **labels):
    return REGISTRY.get_sample_value(name, labels) or 0


def charge(order_id=1, amount="100.00"):
    return ChargeRequest(order_id=order_id, user_id=10, amount=Decimal(amount))


@pytest.mark.parametrize("config", [
    "deploy/prometheus/alerts.yml",
    "deploy/grafana/dashboards/sfmshop-service.json",
])
def test_alerts_and_dashboard_reference_only_exported_metrics(config):
    exported = set()
    for value in vars(metrics).values():
        if isinstance(value, Counter):
            exported.add(f"{value._name}_total")
        elif isinstance(value, Histogram):
            exported |= {f"{value._name}_bucket", f"{value._name}_count", f"{value._name}_sum"}

    text = (REPO_ROOT / config).read_text(encoding="utf-8")
    referenced = set(re.findall(r"payment_service_[a-z_]+_(?:total|bucket|count|sum)\b", text))

    assert referenced
    assert referenced <= exported, sorted(referenced - exported)


def test_prometheus_scrapes_payment_service_metrics_port():
    text = (REPO_ROOT / "deploy/prometheus/prometheus.yml").read_text(encoding="utf-8")

    assert "job_name: payment-service" in text
    assert '"payment:9101"' in text


@pytest.mark.anyio
async def test_charge_outcomes_and_amount_are_counted(service_in):
    async with service_in() as service:
        await service.top_up("top-up-1", 10, Decimal("150.00"))

    success, failed, replay = (sample("payment_service_charges_total", result=r) for r in ("success", "failed", "replay"))
    amount = sample("payment_service_charged_amount_total")

    async with service_in() as service:
        await service.charge("key-1", charge(amount="100.25"))
    async with service_in() as service:
        await service.charge("key-1", charge(amount="100.25"))
    async with service_in() as service:
        await service.charge("key-2", charge(order_id=2, amount="100.00"))

    assert sample("payment_service_charges_total", result="success") == success + 1
    assert sample("payment_service_charges_total", result="replay") == replay + 1
    assert sample("payment_service_charges_total", result="failed") == failed + 1
    assert sample("payment_service_charged_amount_total") == pytest.approx(amount + 100.25)


@pytest.mark.anyio
async def test_refunds_and_top_ups_are_counted(service_in):
    credited, top_up_replay = (sample("payment_service_top_ups_total", result=r) for r in ("credited", "replay"))
    refunded, already = (sample("payment_service_refunds_total", result=r) for r in ("refunded", "already_refunded"))

    for _ in range(2):
        async with service_in() as service:
            await service.top_up("top-up-1", 10, Decimal("100.00"))
    async with service_in() as service:
        payment, _ = await service.charge("key-1", charge())
    for _ in range(2):
        async with service_in() as service:
            await service.refund(payment.id)

    assert sample("payment_service_top_ups_total", result="credited") == credited + 1
    assert sample("payment_service_top_ups_total", result="replay") == top_up_replay + 1
    assert sample("payment_service_refunds_total", result="refunded") == refunded + 1
    assert sample("payment_service_refunds_total", result="already_refunded") == already + 1


@pytest.mark.anyio
async def test_http_metrics_use_route_template_and_skip_probes():
    route = "/api/v1/wallets/{user_id}"
    before = sample("payment_service_http_requests_total", method="GET", route=route, status="401")
    unmatched = sample("payment_service_http_requests_total", method="GET", route="unmatched", status="404")
    probes = sample("payment_service_http_requests_total", method="GET", route="/health/live", status="200")

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://payment") as client:
        assert (await client.get("/api/v1/wallets/10")).status_code == 401
        assert (await client.get("/api/v1/wallets/11")).status_code == 401
        assert (await client.get("/nope")).status_code == 404
        assert (await client.get("/health/live")).status_code == 200

    assert sample("payment_service_http_requests_total", method="GET", route=route, status="401") == before + 2
    assert sample("payment_service_http_requests_total", method="GET", route="unmatched", status="404") == unmatched + 1
    assert sample("payment_service_http_requests_total", method="GET", route="/health/live", status="200") == probes
    assert sample("payment_service_http_request_duration_seconds_count", method="GET", route=route) >= 2


def test_metrics_server_is_optional_and_survives_busy_port():
    assert start_metrics_server(None) is False
    assert start_metrics_server(0) is False

    with socket.socket() as busy:
        busy.bind(("0.0.0.0", 0))
        busy.listen()
        assert start_metrics_server(busy.getsockname()[1]) is False


def test_exposition_has_no_created_timestamp_series():
    from prometheus_client import generate_latest

    metrics.CHARGES.labels("success").inc(0)
    body = generate_latest(REGISTRY).decode()

    assert "payment_service_charges_total" in body
    assert not re.search(r"^\w+_created[{ ]", body, flags=re.MULTILINE)
