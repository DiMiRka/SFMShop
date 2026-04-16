from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
import uvicorn
import time
from loguru import logger

from src.api.v1 import v1_router
from src.core.config import app_settings, uvicorn_options
from src.core.limiter import limiter
from src.services.log_service import setup_logging
from src.api.exceptions import (validation_notfound_handler, validation_exception_handler,
                                business_exception_handler, unauthorized_handler, base_exception_handler)
from src.models.exceptions import (ValidationError, NotFoundError, BusinessLogicError, UnauthorizedError)


app = FastAPI(
    title="SFMShop API",
    description="API для интернет магазина SFMShop",
    version="1.0.0"
)

app.include_router(v1_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=app_settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()

    logger.info(f"Запрос: {request.method} {request.url.path}")

    try:
        response = await call_next(request)
    except Exception as e:
        logger.exception(f"Необработанная ошибка: {e}", exc_info=True)

        return JSONResponse(
            status_code=500,
            content={"detail": "Внутренняя ошибка сервера"}
        )

    process_time = time.time() - start_time
    logger.info(f"Ответ: {response.status_code}, время обработки: {process_time:.3f} сек")

    response.headers["X-Process-Time"] = str(process_time)

    return response

app.state.limiter = limiter
app.add_exception_handler(
    RateLimitExceeded,
    _rate_limit_exceeded_handler,
)

app.add_exception_handler(ValidationError, validation_exception_handler)
app.add_exception_handler(NotFoundError, validation_notfound_handler)
app.add_exception_handler(UnauthorizedError, unauthorized_handler)
app.add_exception_handler(BusinessLogicError, business_exception_handler)
app.add_exception_handler(Exception, base_exception_handler)

if __name__ == "__main__":
    setup_logging()
    logger.info("Сервер запущен")
    uvicorn.run("src.api.main:app", **uvicorn_options)
