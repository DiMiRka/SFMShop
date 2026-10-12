from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from payment.database.connection import get_session

health_router = APIRouter(prefix="/health", tags=["health"])


@health_router.get("/live", summary="Процесс жив")
async def live():
    return {"status": "ok"}


@health_router.get("/ready", summary="Сервис готов принимать трафик")
async def ready(session: Annotated[AsyncSession, Depends(get_session)], response: Response):
    try:
        await session.execute(text("SELECT 1"))
    except Exception as exc:
        logger.warning(f"payment_db_unavailable error={exc!r}")
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "fail", "checks": {"postgres": "fail"}}
    return {"status": "ok", "checks": {"postgres": "ok"}}
