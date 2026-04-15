from fastapi import APIRouter, Depends, Request
from fastapi.security import OAuth2PasswordRequestForm

from src.schemas import UserCreate, UserResponse, Token
from src.core.dependencies import user_write_service, user_read_service
from src.core.config import app_settings
from src.core.limiter import limiter

auth_router = APIRouter(prefix="/auth", tags=["authentication"])


@auth_router.post("/register", response_model=UserResponse)
async def register(service: user_write_service, user_data: UserCreate):
    return await service.register_user(user_data)


@auth_router.post("/login", response_model=Token)
@limiter.limit(app_settings.rate_limit_login)
async def login(request: Request, service: user_read_service, form_data: OAuth2PasswordRequestForm = Depends()):
    return await service.authorized_user(form_data)


@auth_router.post("/refresh", response_model=Token)
async def refresh_token(service: user_read_service, refresh_token: str):
    return await service.create_access_token_db(refresh_token)
