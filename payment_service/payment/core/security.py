import hmac
from typing import Annotated

from fastapi import Header, HTTPException, status

from payment.core.config import settings


async def require_service_token(x_service_token: Annotated[str | None, Header()] = None) -> None:
    expected = settings.service_token
    if not expected or x_service_token is None or not hmac.compare_digest(x_service_token, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный сервисный токен")
