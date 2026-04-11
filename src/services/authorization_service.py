from fastapi import HTTPException, Depends, Header, status


async def authorization_user(x_token: str | None = Header(None, alias="X-Token")):
    if not x_token or not x_token.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется токен аутентификации"
        )

    token = x_token.replace("Bearer ", "")

    if token != "valid_token":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный токен"
        )
