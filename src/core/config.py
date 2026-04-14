import multiprocessing
import os
from dotenv import load_dotenv
from pydantic import PostgresDsn, RedisDsn
from pydantic_core import MultiHostUrl
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class AppSettings(BaseSettings):
    app_port: int = 8000
    app_host: str = 'localhost'
    reload: bool = True
    cpu_count: int | None = None

    mongo_url: str = os.getenv('MONGO_URL')

    algorithm: str = 'HS256'
    jwt_secret: str = os.getenv('JWT_SECRET')
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    cors_origins: list[str] = os.getenv("CORS_ORIGINS").split(",")

    rate_limit_login = os.getenv('RATE_LIMIT_LOGIN')

    @property
    def postgres_url(self) -> str:
        return (f"postgresql+asyncpg://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@"
                f"{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}")

    @property
    def postgres_replica_url(self) -> str:
        return f"postgresql+asyncpg://{os.getenv('DB_REPLICA_USER')}:{os.getenv('DB_REPLICA_PASSWORD')}@"\
               f"{os.getenv('DB_REPLICA_HOST')}:{os.getenv('DB_REPLICA_PORT')}/{os.getenv('DB_REPLICA_NAME')}"

    @property
    def redis_url(self) -> str:
        return f"redis://{os.getenv("REDIS_HOST")}:{os.getenv("REDIS_PORT")}/{os.getenv("REDIS_DB")}"

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="allow",
    )


app_settings = AppSettings()

uvicorn_options = {
    "host": app_settings.app_host,
    "port": app_settings.app_port,
    "workers": app_settings.cpu_count or multiprocessing.cpu_count(),
    "reload": app_settings.reload,
}


