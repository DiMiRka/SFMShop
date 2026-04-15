from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Annotated

from src.database.models import User
from src.schemas import TokenData
from src.core.security import decode_token
from src.repositories import ProductRepository, OrderRepository, UserRepository
from src.services import ProductService, UserService, OrderService
from src.database import get_write_session, get_read_session, redis_client

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


async def get_product_write_repository(db: write_db_dependency) -> ProductRepository:
    return ProductRepository(db)


async def get_product_read_repository(db: read_db_dependency) -> ProductRepository:
    return ProductRepository(db)

p_rep_write_dependency = Annotated[ProductRepository, Depends(get_product_write_repository)]
p_rep_read_dependency = Annotated[ProductRepository, Depends(get_product_read_repository)]


async def get_order_write_repository(db: write_db_dependency) -> OrderRepository:
    return OrderRepository(db)


async def get_order_read_repository(db: read_db_dependency) -> OrderRepository:
    return OrderRepository(db)

o_rep_write_dependency = Annotated[OrderRepository, Depends(get_order_write_repository)]
o_rep_read_dependency = Annotated[OrderRepository, Depends(get_order_read_repository)]


async def get_user_write_repository(db: write_db_dependency) -> UserRepository:
    return UserRepository(db)


async def get_user_read_repository(db: read_db_dependency) -> UserRepository:
    return UserRepository(db)

u_rep_write_dependency = Annotated[UserRepository, Depends(get_user_write_repository)]
u_rep_read_dependency = Annotated[UserRepository, Depends(get_user_read_repository)]


async def get_product_write_service(rep: p_rep_write_dependency) -> ProductService:
    return ProductService(rep, redis_client)


async def get_product_read_service(rep: p_rep_read_dependency) -> ProductService:
    return ProductService(rep, redis_client)

product_write_service = Annotated[ProductService, Depends(get_product_write_service)]
product_read_service = Annotated[ProductService, Depends(get_product_read_service)]


async def get_user_write_service(u_rep: u_rep_write_dependency, o_rep: o_rep_write_dependency) -> UserService:
    return UserService(u_rep, o_rep, redis_client)


async def get_user_read_service(u_rep: u_rep_read_dependency, o_rep: o_rep_read_dependency) -> UserService:
    return UserService(u_rep, o_rep, redis_client)


user_write_service = Annotated[UserService, Depends(get_user_write_service)]
user_read_service = Annotated[UserService, Depends(get_user_read_service)]


async def get_order_write_service(
        o_rep: o_rep_write_dependency,
        u_rep: u_rep_write_dependency,
        p_rep: p_rep_write_dependency
) -> OrderService:
    return OrderService(o_rep, u_rep, p_rep, redis_client)


async def get_order_read_service(
        o_rep: o_rep_read_dependency,
        u_rep: u_rep_read_dependency,
        p_rep: p_rep_read_dependency
) -> OrderService:
    return OrderService(o_rep, u_rep, p_rep, redis_client)

order_write_service = Annotated[OrderService, Depends(get_order_write_service)]
order_read_service = Annotated[OrderService, Depends(get_order_read_service)]
