from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Request, status
from fastapi.responses import JSONResponse
from loguru import logger

from payment.api.health import health_router
from payment.api.payments import payments_router
from payment.api.wallets import wallets_router
from payment.core.config import settings
from payment.core.exceptions import ConflictError, IdempotencyKeyReusedError, NotFoundError
from payment.database.connection import engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not settings.service_token:
        logger.warning("PAYMENT_SERVICE_TOKEN is empty: every API request will be rejected")
    yield
    await engine.dispose()


app = FastAPI(title="SFMShop Payment Service", version="1.0.0", lifespan=lifespan)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(payments_router)
api_router.include_router(wallets_router)
app.include_router(api_router)
app.include_router(health_router)

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
