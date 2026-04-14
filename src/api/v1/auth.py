from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm

from src.schemas import UserCreate, UserResponse, Token
from src.database import create_user_db, get_authorized_user, create_access_token_db
from src.core.dependencies import write_db_dependency, read_db_dependency
from src.core.config import app_settings
from src.api.main import limiter

auth_router = APIRouter(prefix="/auth", tags=["authentication"])


@auth_router.post("/register", response_model=UserResponse)
async def register(db: write_db_dependency, user_data: UserCreate):
    await create_user_db(db, user_data)


@auth_router.post("/login", response_model=Token)
@limiter.limit(app_settings.rate_limit_login)
async def login(db: read_db_dependency, form_data: OAuth2PasswordRequestForm = Depends()):
    await get_authorized_user(db, form_data)


@auth_router.post("/refresh", response_model=Token)
async def refresh_token(db: read_db_dependency, refresh_token: str):
    await create_access_token_db(db, refresh_token)
