from collections.abc import Mapping
from typing import Any

from loguru import logger
from prometheus_client import Counter, Histogram, disable_created_metrics, start_http_server


disable_created_metrics()

HTTP_REQUESTS = Counter(
    "payment_service_http_requests_total",
    "HTTP-запросы к payment-service по маршруту, методу и коду ответа",
    ["method", "route", "status"],
)
HTTP_DURATION = Histogram(
    "payment_service_http_request_duration_seconds",
    "Время обработки HTTP-запроса в payment-service",
    ["method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
)
CHARGES = Counter(
    "payment_service_charges_total",
    "Списания за заказы: success, failed (не хватило денег), replay (повтор ключа или заказ уже оплачен)",
    ["result"],
)
CHARGED_AMOUNT = Counter(
    "payment_service_charged_amount_total",
    "Сумма успешных списаний в рублях",
)
REFUNDS = Counter(
    "payment_service_refunds_total",
    "Возвраты: refunded, already_refunded",
    ["result"],
)
TOP_UPS = Counter(
    "payment_service_top_ups_total",
    "Пополнения кошелька: credited, replay",
    ["result"],
)

UNMATCHED_ROUTE = "unmatched"
PROBE_PATHS = frozenset({"/health/live", "/health/ready"})


def route_label(scope: Mapping[str, Any]) -> str:
    route = scope.get("route")
    return getattr(route, "path_format", None) or UNMATCHED_ROUTE


def start_metrics_server(port: int | None) -> bool:
    if not port:
        return False

    try:
        start_http_server(port)
    except OSError as exc:
        logger.warning(f"metrics_server_not_started port={port} error={exc!r}")
        return False

    logger.info(f"metrics_server_started port={port}")
    return True
