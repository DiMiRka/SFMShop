from contextlib import asynccontextmanager
from typing import Any, cast
from fastapi import FastAPI, Request
import redis
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
import uvicorn
import time

from sfmshop.api.health import health_router
from sfmshop.api.v1 import v1_router
from sfmshop.clients.llm import create_llm_client
from sfmshop.clients.payment_client import create_payment_client
from sfmshop.database.connection import create_mongo_client
from sfmshop.repositories.event_repository import EventRepository
from sfmshop.core.config import app_settings, uvicorn_options
from sfmshop.core.metrics import HTTP_DURATION, HTTP_REQUESTS, route_label, start_metrics_server
from sfmshop.core.limiter import limiter
from sfmshop.services.cache_service import CacheService
from sfmshop.services.log_service import configure_sentry, log_service, setup_logging
from sfmshop.services.queue_producer import QueueProducer
from sfmshop.services.queue_consumer import QueueConsumer
from sfmshop.api.exceptions import (validation_notfound_handler, validation_exception_handler,
                                business_exception_handler, unauthorized_handler, forbidden_handler,
                                service_unavailable_handler, base_exception_handler)
from sfmshop.core.exceptions import (ValidationError, NotFoundError, BusinessLogicError, UnauthorizedError,
                                   ForbiddenError, ServiceUnavailableError)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    configure_sentry(app_settings.sentry_dsn)
    log_service.info("application_starting")
    start_metrics_server(app_settings.metrics_port)

    app.state.redis = redis.asyncio.Redis.from_url(
        app_settings.redis_url, socket_connect_timeout=0.5, socket_timeout=1.0,
    )
    try:
        await app.state.redis.ping()
    except redis.exceptions.RedisError as exc:
        log_service.warning("redis_unavailable_on_startup", error=repr(exc))

    app.state.queue = await QueueProducer.get_instance(
        app_settings.rabbitmq_url,
        max_retries=app_settings.rabbitmq_max_retries,
        base_delay=app_settings.rabbitmq_base_delay,
        backoff_multiplier=app_settings.rabbitmq_backoff_multiplier,
    )
    app.state.cache = CacheService(app.state.redis)
    app.state.llm_client = create_llm_client(app_settings)
    app.state.payment_client = create_payment_client(app_settings)

    app.state.mongo = create_mongo_client(app_settings.mongo_url)
    app.state.events = EventRepository(app.state.mongo[app_settings.mongo_db]["events"])
    try:
        await app.state.events.ensure_indexes(app_settings.event_log_ttl_days)
    except Exception as exc:
        log_service.warning("event_log_indexes_failed", error=repr(exc))

    consumer = QueueConsumer(
        cache=app.state.cache,
        url=app_settings.rabbitmq_url,
        events=app.state.events,
    )
    await consumer.start()

    app.state.consumer = consumer

    yield

    await app.state.consumer.close()

    if getattr(app.state.queue, "connection", None):
        await app.state.queue.close()

    await app.state.redis.close()
    if app.state.llm_client is not None:
        await app.state.llm_client.close()
    if app.state.payment_client is not None:
        await app.state.payment_client.close()
    await app.state.mongo.close()
    log_service.info("application_stopped")

sfmshop_app = FastAPI(
    title="SFMShop API",
    description="SFMShop API",
    version="1.0.0",
    lifespan=lifespan,
    debug=app_settings.debug,
)

sfmshop_app.include_router(v1_router)
sfmshop_app.include_router(health_router)

sfmshop_app.add_middleware(
    CORSMiddleware,
    allow_origins=app_settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["*"],
)


@sfmshop_app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    path = request.url.path
    method = request.method
    client = getattr(request, "client", None)
    client_host = client.host if client else None
    is_probe = path.startswith("/health")

    (log_service.debug if is_probe else log_service.info)(
        "http_request_started",
        method=method,
        path=path,
        client_host=client_host,
    )

    try:
        response = await call_next(request)
    except Exception as exc:
        process_time = time.time() - start_time
        if not is_probe:
            route = route_label(request.scope)
            HTTP_REQUESTS.labels(method, route, "500").inc()
            HTTP_DURATION.labels(method, route).observe(process_time)
        log_service.error(
            "http_request_failed",
            exception=exc,
            method=method,
            path=path,
            client_host=client_host,
            process_time=round(process_time, 3),
        )
        raise

    process_time = time.time() - start_time
    if not is_probe:
        route = route_label(request.scope)
        HTTP_REQUESTS.labels(method, route, str(response.status_code)).inc()
        HTTP_DURATION.labels(method, route).observe(process_time)

    log_fields = {
        "method": method,
        "path": path,
        "status_code": response.status_code,
        "client_host": client_host,
        "process_time": round(process_time, 3),
    }

    if is_probe and response.status_code < 400:
        log_service.debug("http_request_completed", **log_fields)
    elif response.status_code >= 500:
        log_service.error("http_request_server_error", **log_fields)
    elif response.status_code >= 400:
        log_service.warning("http_request_client_error", **log_fields)
    else:
        log_service.info("http_request_completed", **log_fields)

    response.headers["X-Process-Time"] = str(process_time)

    return response

sfmshop_app.state.limiter = limiter
sfmshop_app.add_exception_handler(
    RateLimitExceeded,
    cast(Any, _rate_limit_exceeded_handler),
)

sfmshop_app.add_exception_handler(ValidationError, cast(Any, validation_exception_handler))
sfmshop_app.add_exception_handler(NotFoundError, cast(Any, validation_notfound_handler))
sfmshop_app.add_exception_handler(UnauthorizedError, cast(Any, unauthorized_handler))
sfmshop_app.add_exception_handler(ForbiddenError, cast(Any, forbidden_handler))
sfmshop_app.add_exception_handler(BusinessLogicError, cast(Any, business_exception_handler))
sfmshop_app.add_exception_handler(ServiceUnavailableError, cast(Any, service_unavailable_handler))
sfmshop_app.add_exception_handler(Exception, cast(Any, base_exception_handler))

if __name__ == "__main__":
    log_service.info("server_started")
    uvicorn.run("sfmshop.api.main:sfmshop_app", **uvicorn_options)
