from typing import Any, cast

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from sfmshop.core.config import app_settings
from sfmshop.core.security import decode_token_sync


def user_or_ip(request: Request) -> str:
    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() == "bearer" and token:
        payload = decode_token_sync(token) or {}
        if user_id := payload.get("sub"):
            return f"user:{user_id}"
    return get_remote_address(request)


def create_limiter(storage_uri: str) -> Limiter:
    return Limiter(
        key_func=get_remote_address,
        storage_uri=storage_uri,
        storage_options=cast(Any, {"socket_connect_timeout": 0.3, "socket_timeout": 0.3}),
        in_memory_fallback_enabled=True,
    )


limiter = create_limiter(app_settings.rate_limit_storage_uri)
