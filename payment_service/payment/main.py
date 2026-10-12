import time
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Request, status
from fastapi.responses import JSONResponse
from loguru import logger

from payment.api.health import health_router
from payment.api.payments import payments_router
from payment.api.wallets import wallets_router
from payment.core.config import settings
from payment.core.exceptions import ConflictError, IdempotencyKeyReusedError, NotFoundError
from payment.core.metrics import HTTP_DURATION, HTTP_REQUESTS, PROBE_PATHS, route_label, start_metrics_server
from payment.database.connection import engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not settings.service_token:
        logger.warning("PAYMENT_SERVICE_TOKEN is empty: every API request will be rejected")
    start_metrics_server(settings.metrics_port)
    yield
    await engine.dispose()


app = FastAPI(title="SFMShop Payment Service", version="1.0.0", lifespan=lifespan)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(payments_router)
api_router.include_router(wallets_router)
app.include_router(api_router)
app.include_router(health_router)


@app.middleware("http")
async def record_metrics(request: Request, call_next):
    if request.url.path in PROBE_PATHS:
        return await call_next(request)

    started = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        route = route_label(request.scope)
        HTTP_REQUESTS.labels(request.method, route, str(status_code)).inc()
        HTTP_DURATION.labels(request.method, route).observe(time.perf_counter() - started)

ERROR_STATUSES = {
    NotFoundError: status.HTTP_404_NOT_FOUND,
    ConflictError: status.HTTP_409_CONFLICT,
    IdempotencyKeyReusedError: status.HTTP_422_UNPROCESSABLE_CONTENT,
}


def make_handler(code: int):
    async def handler(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=code, content={"detail": str(exc)})
    return handler


for error, code in ERROR_STATUSES.items():
    app.add_exception_handler(error, make_handler(code))
