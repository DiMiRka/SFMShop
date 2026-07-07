from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
import redis
import httpx
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
import uvicorn
import time
import os

from src.api.v1 import v1_router
from src.core.config import app_settings, uvicorn_options
from src.core.limiter import limiter
from src.services.cache_service import CacheService
from src.services.log_service import configure_sentry, log_service, setup_logging
from src.services.queue_producer import QueueProducer
from src.services.queue_consumer import QueueConsumer
from src.api.exceptions import (validation_notfound_handler, validation_exception_handler,
                                business_exception_handler, unauthorized_handler, base_exception_handler)
from src.models.exceptions import (ValidationError, NotFoundError, BusinessLogicError, UnauthorizedError)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    configure_sentry(os.getenv("SENTRY_DSN"))
    log_service.info("Запуск приложения")

    app.state.redis = redis.asyncio.Redis.from_url(app_settings.redis_url)
    await app.state.redis.ping()

    app.state.http_client = httpx.AsyncClient(timeout=5)
    app.state.queue = await QueueProducer.get_instance()
    app.state.cache = CacheService(app.state.redis)

    consumer = QueueConsumer(cache=app.state.cache)
    await consumer.start()

    app.state.consumer = consumer

    yield

    if getattr(app.state.queue, "connection", None):
        await app.state.queue.close()

    await app.state.redis.close()
    await app.state.http_client.aclose()
    log_service.info("Приложение завершило работу")

sfmshop_app = FastAPI(
    title="SFMShop API",
    description="API для интернет магазина SFMShop",
    version="1.0.0",
    lifespan=lifespan,
)

sfmshop_app.include_router(v1_router)

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

    log_service.info(
        "HTTP запрос обрабатывается",
        method=method,
        path=path,
        client_host=client_host,
    )

    try:
        response = await call_next(request)
    except Exception as exc:
        process_time = time.time() - start_time
        log_service.error(
            "HTTP ошибка запроса",
            exception=exc,
            method=method,
            path=path,
            client_host=client_host,
            process_time=round(process_time, 3),
        )
        raise

    process_time = time.time() - start_time
    log_fields = {
        "method": method,
        "path": path,
        "status_code": response.status_code,
        "client_host": client_host,
        "process_time": round(process_time, 3),
    }

    if response.status_code >= 500:
        log_service.error("HTTP запрос ошибка сервера", **log_fields)
    elif response.status_code >= 400:
        log_service.warning("HTTP запрос ошибка клиента", **log_fields)
    else:
        log_service.info("HTTP запрос обработан", **log_fields)

    response.headers["X-Process-Time"] = str(process_time)

    return response

sfmshop_app.state.limiter = limiter
sfmshop_app.add_exception_handler(
    RateLimitExceeded,
    _rate_limit_exceeded_handler,
)

sfmshop_app.add_exception_handler(ValidationError, validation_exception_handler)
sfmshop_app.add_exception_handler(NotFoundError, validation_notfound_handler)
sfmshop_app.add_exception_handler(UnauthorizedError, unauthorized_handler)
sfmshop_app.add_exception_handler(BusinessLogicError, business_exception_handler)
sfmshop_app.add_exception_handler(Exception, base_exception_handler)

if __name__ == "__main__":
    log_service.info("Сервер запущен")
    uvicorn.run("src.api.main:sfmshop_app", **uvicorn_options)
