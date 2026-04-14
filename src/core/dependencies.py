from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Annotated

from src.database.models import User
from src.schemas import TokenData
from src.core.security import decode_token
from src.database import get_write_session, get_read_session

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/v1/auth/login")


write_db_dependency = Annotated[AsyncSession, Depends(get_write_session)]
read_db_dependency = Annotated[AsyncSession, Depends(get_read_session)]


async def get_current_user(db: read_db_dependency, token: str = Depends(oauth2_scheme)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = await decode_token(token)
    if payload is None:
        raise credentials_exception

    user_id = payload.get("sub")
    if user_id is None:
        raise credentials_exception

    token_data = TokenData(user_id=int(user_id))

    results = await db.execute(select(User).where(User.id == token_data.user_id))
    user = results.scalar_one_or_none()

    if user is None:
        raise credentials_exception

    return user

current_user = Annotated[User, Depends(get_current_user)]
