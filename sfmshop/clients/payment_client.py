import asyncio
import uuid
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Any

import httpx
from pydantic import BaseModel

from sfmshop.core.config import AppSettings
from sfmshop.core.exceptions import PaymentUnavailableError, ValidationError
from sfmshop.core.metrics import PAYMENT_REQUESTS
from sfmshop.services.log_service import log_service


PAYMENTS_PATH = "/api/v1/payments"
WALLETS_PATH = "/api/v1/wallets"
RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})
CENTS = Decimal("0.01")


class PaymentStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"


class PaymentResponse(BaseModel):
    id: int
    order_id: int
    status: PaymentStatus


class WalletResponse(BaseModel):
    user_id: int
    balance: Decimal


@dataclass(frozen=True)
class PaymentResult:
    status: PaymentStatus
    payment_id: int | None = None
    detail: str | None = None


def money(amount: Decimal) -> str:
    return str(amount.quantize(CENTS))


class PaymentClient:
    def __init__(
            self,
            http_client: httpx.AsyncClient,
            max_retries: int = 3,
            base_delay: float = 0.5,
            max_delay: float = 5.0):
        self.http_client = http_client
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay

    async def charge(self, order_id: int, user_id: int, amount: Decimal) -> PaymentResult:
        payload = {"order_id": order_id, "user_id": user_id, "amount": money(amount)}
        try:
            response = await self._send("POST", PAYMENTS_PATH, json=payload, idempotency_key=uuid.uuid4().hex)
        except PaymentUnavailableError:
            PAYMENT_REQUESTS.labels(result="unavailable").inc()
            raise

        return self._to_result(order_id, response)

    async def refund(self, payment_id: int) -> None:
        response = await self._send("POST", f"{PAYMENTS_PATH}/{payment_id}/refund")
        response.raise_for_status()

    async def get_balance(self, user_id: int) -> Decimal:
        response = await self._send("GET", f"{WALLETS_PATH}/{user_id}")
        response.raise_for_status()
        return WalletResponse.model_validate(response.json()).balance

    async def top_up(self, user_id: int, amount: Decimal, idempotency_key: str) -> Decimal:
        response = await self._send("POST", f"{WALLETS_PATH}/{user_id}/top-up",
                                    json={"amount": money(amount)}, idempotency_key=idempotency_key)
        if response.status_code == httpx.codes.UNPROCESSABLE_ENTITY:
            raise ValidationError(response.json().get("detail", "Ключ идемпотентности уже использован"))
        response.raise_for_status()
        return WalletResponse.model_validate(response.json()).balance

    async def close(self) -> None:
        await self.http_client.aclose()

    async def _send(
            self,
            method: str,
            path: str,
            json: dict[str, Any] | None = None,
            idempotency_key: str | None = None) -> httpx.Response:
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else {}
        reason = ""

        for attempt in range(self.max_retries + 1):
            try:
                response = await self.http_client.request(method, path, json=json, headers=headers)
            except httpx.TransportError as exc:
                reason = type(exc).__name__
            else:
                if response.status_code not in RETRYABLE_STATUSES:
                    return response
                reason = f"http_{response.status_code}"

            if attempt < self.max_retries:
                log_service.warning("payment_retry", path=path, attempt=attempt + 1, reason=reason)
                await asyncio.sleep(min(self.base_delay * 2 ** attempt, self.max_delay))

        log_service.warning("payment_unavailable", path=path, reason=reason)
        raise PaymentUnavailableError("Сервис оплаты временно недоступен")

    @staticmethod
    def _to_result(order_id: int, response: httpx.Response) -> PaymentResult:
        if response.status_code == httpx.codes.CONFLICT:
            body = response.json()
            PAYMENT_REQUESTS.labels(result=PaymentStatus.FAILED).inc()
            return PaymentResult(PaymentStatus.FAILED, payment_id=body.get("id"), detail=body.get("detail"))

        response.raise_for_status()
        payment = PaymentResponse.model_validate(response.json())

        if payment.order_id != order_id:
            raise ValueError(f"Payment {payment.id} belongs to order {payment.order_id}, expected {order_id}")

        PAYMENT_REQUESTS.labels(result=payment.status).inc()
        return PaymentResult(payment.status, payment_id=payment.id)


def create_payment_client(settings: AppSettings) -> PaymentClient | None:
    if not settings.payment_service_url:
        return None

    http_client = httpx.AsyncClient(
        base_url=settings.payment_service_url,
        timeout=httpx.Timeout(settings.payment_timeout, connect=settings.payment_connect_timeout),
        headers={"X-Service-Token": settings.payment_service_token},
    )
    return PaymentClient(http_client, max_retries=settings.payment_max_retries)
