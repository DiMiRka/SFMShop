import json
from decimal import Decimal

import httpx
import pytest
from prometheus_client import REGISTRY

from sfmshop.clients import payment_client
from sfmshop.clients.payment_client import PaymentClient, PaymentResult, PaymentStatus, create_payment_client
from sfmshop.core.config import AppSettings
from sfmshop.core.exceptions import PaymentUnavailableError, ServiceUnavailableError


pytestmark = pytest.mark.anyio


class Transport:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        status, body = response
        return httpx.Response(status, json=body)

    def keys(self):
        return [request.headers["Idempotency-Key"] for request in self.requests]


@pytest.fixture
def delays(monkeypatch):
    recorded = []

    async def fake_sleep(delay):
        recorded.append(delay)

    monkeypatch.setattr(payment_client.asyncio, "sleep", fake_sleep)
    return recorded


def make_client(transport, max_retries=3):
    http_client = httpx.AsyncClient(base_url="http://payment", transport=httpx.MockTransport(transport))
    return PaymentClient(http_client, max_retries=max_retries, base_delay=0.5, max_delay=1.5)


def payments(result):
    return REGISTRY.get_sample_value("sfmshop_payment_requests_total", {"result": result}) or 0


async def test_success_sends_contract_payload_with_amount_as_string(delays):
    transport = Transport((201, {"id": 100, "order_id": 7, "status": "success"}))
    before = payments("success")

    result = await make_client(transport).charge(7, 3, Decimal("150.5"))

    assert result == PaymentResult(PaymentStatus.SUCCESS, payment_id=100)
    [request] = transport.requests
    assert request.method == "POST" and request.url == "http://payment/api/v1/payments"
    assert json.loads(request.content) == {"order_id": 7, "user_id": 3, "amount": "150.50"}
    assert len(request.headers["Idempotency-Key"]) == 32
    assert delays == []
    assert payments("success") == before + 1


async def test_declined_payment_is_a_result_not_a_retry(delays):
    transport = Transport((409, {"detail": "Недостаточно средств"}))
    before = payments("failed")

    result = await make_client(transport).charge(7, 3, Decimal("10.00"))

    assert result == PaymentResult(PaymentStatus.FAILED, detail="Недостаточно средств")
    assert len(transport.requests) == 1
    assert payments("failed") == before + 1


@pytest.mark.parametrize("first_failure", [
    (503, {"detail": "busy"}),
    (429, {"detail": "slow down"}),
    httpx.ReadTimeout("no answer"),
    httpx.ConnectError("refused"),
])
async def test_retry_reuses_idempotency_key(delays, first_failure):
    transport = Transport(first_failure, (201, {"id": 100, "order_id": 7, "status": "success"}))

    result = await make_client(transport).charge(7, 3, Decimal("10.00"))

    assert result.status == PaymentStatus.SUCCESS
    first_key, retry_key = transport.keys()
    assert first_key == retry_key
    assert delays == [0.5]


async def test_unavailable_after_all_retries_with_capped_backoff(delays):
    transport = Transport(*[httpx.ConnectError("refused")] * 4)
    before = payments("unavailable")

    with pytest.raises(PaymentUnavailableError):
        await make_client(transport, max_retries=3).charge(7, 3, Decimal("10.00"))

    assert len(transport.requests) == 4
    assert delays == [0.5, 1.0, 1.5]
    assert payments("unavailable") == before + 1
    assert issubclass(PaymentUnavailableError, ServiceUnavailableError)


async def test_each_charge_gets_its_own_idempotency_key(delays):
    body = {"id": 100, "order_id": 7, "status": "failed"}
    transport = Transport((200, body), (200, body))
    client = make_client(transport)

    await client.charge(7, 3, Decimal("10.00"))
    await client.charge(7, 3, Decimal("10.00"))

    first, second = transport.keys()
    assert first != second


@pytest.mark.parametrize("status", [400, 404, 422])
async def test_contract_errors_are_not_retried(delays, status):
    transport = Transport((status, {"detail": "bad"}))

    with pytest.raises(httpx.HTTPStatusError):
        await make_client(transport).charge(7, 3, Decimal("10.00"))

    assert len(transport.requests) == 1


async def test_payment_for_another_order_is_rejected(delays):
    transport = Transport((201, {"id": 100, "order_id": 8, "status": "success"}))

    with pytest.raises(ValueError):
        await make_client(transport).charge(7, 3, Decimal("10.00"))


async def test_factory_builds_one_shared_client_only_when_url_is_set():
    assert create_payment_client(AppSettings(payment_service_url=None)) is None

    client = create_payment_client(AppSettings(
        payment_service_url="http://payment-service:8001",
        payment_timeout=4.0,
        payment_connect_timeout=1.0,
        payment_max_retries=2,
    ))

    assert client is not None
    assert str(client.http_client.base_url) == "http://payment-service:8001"
    assert client.http_client.timeout == httpx.Timeout(4.0, connect=1.0)
    assert client.max_retries == 2

    await client.close()
    assert client.http_client.is_closed
