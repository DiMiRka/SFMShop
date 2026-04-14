from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn
import time
from loguru import logger

from src.api.v1 import v1_router
from src.services.log_service import setup_logging

setup_logging()


app = FastAPI(
    title="SFMShop API",
    description="API для интернет магазина SFMShop",
    version="1.0.0"
)

app.include_router(v1_router)


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


if __name__ == "__main__":
    setup_logging()
    logger.info("Сервер запущен")
    uvicorn.run("src.api.main:app", reload=True, log_level="critical")
