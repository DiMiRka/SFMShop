from fastapi import APIRouter, Response, status

from src.core.dependencies import health_service

health_router = APIRouter(prefix="/health", tags=["health"])


@health_router.get("/live", summary="Процесс жив")
async def live():
    return {"status": "ok"}


@health_router.get("/ready", summary="Приложение готово принимать трафик")
async def ready(service: health_service, response: Response):
    result = await service.readiness()
    if result["status"] == "fail":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return result
