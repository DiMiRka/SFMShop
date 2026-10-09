from collections.abc import Mapping
from typing import Any

from prometheus_client import Counter, Histogram, disable_created_metrics, start_http_server

from sfmshop.services.log_service import log_service


disable_created_metrics()

HTTP_REQUESTS = Counter(
    "sfmshop_http_requests_total",
    "HTTP-запросы по маршруту, методу и коду ответа",
    ["method", "route", "status"],
)
HTTP_DURATION = Histogram(
    "sfmshop_http_request_duration_seconds",
    "Время обработки HTTP-запроса",
    ["method", "route"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
)
CACHE_REQUESTS = Counter(
    "sfmshop_cache_requests_total",
    "Обращения к кэшу: hit, miss, error (Redis недоступен), skipped (пауза после ошибки)",
    ["result"],
)
EVENTS_PUBLISHED = Counter(
    "sfmshop_events_published_total",
    "Публикация событий в RabbitMQ",
    ["routing_key", "result"],
)
ORDERS_CREATED = Counter(
    "sfmshop_orders_created_total",
    "Созданные заказы",
)
PAYMENT_REQUESTS = Counter(
    "sfmshop_payment_requests_total",
    "Запросы к сервису оплаты по исходу: success, failed (отказ), unavailable (после всех повторов)",
    ["result"],
)
ASSISTANT_REQUESTS = Counter(
    "sfmshop_assistant_requests_total",
    "Запросы к ИИ-ассистенту по исходу",
    ["outcome"],
)
ASSISTANT_TOOL_CALLS = Counter(
    "sfmshop_assistant_tool_calls_total",
    "Вызовы инструментов ИИ-ассистента",
    ["tool", "result"],
)

UNMATCHED_ROUTE = "unmatched"


def route_label(scope: Mapping[str, Any]) -> str:
    route = scope.get("route")
    return getattr(route, "path_format", None) or UNMATCHED_ROUTE


def start_metrics_server(port: int | None) -> bool:
    if not port:
        return False

    try:
        start_http_server(port)
    except OSError as exc:
        log_service.warning("metrics_server_not_started", port=port, error=repr(exc))
        return False

    log_service.info("metrics_server_started", port=port)
    return True
