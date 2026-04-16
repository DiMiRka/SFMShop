from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext
from src.core.config import app_settings

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


async def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


async def create_access_token(data: dict, expires_delta: timedelta = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=app_settings.access_token_expire_minutes)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, app_settings.jwt_secret, algorithm=app_settings.algorithm)
    return encoded_jwt


async def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=app_settings.refresh_token_expire_days)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, app_settings.jwt_secret, algorithm=app_settings.algorithm)
    return encoded_jwt


async def decode_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, app_settings.jwt_secret, algorithms=[app_settings.algorithm])
        return payload
    except JWTError:
        return None
