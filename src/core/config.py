import multiprocessing

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    app_port: int = 8000
    app_host: str = "localhost"
    log_level: str = "critical"
    reload: bool = True
    cpu_count: int | None = None

    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "sfmshop"
    db_user: str = "postgres"
    db_password: str = "password"

    db_replica_host: str = "localhost"
    db_replica_port: int = 5432
    db_replica_name: str = "sfmshop"
    db_replica_user: str = "postgres"
    db_replica_password: str = "password"

    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0

    mongo_url: str = "mongodb://localhost:27017"

    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
    rabbitmq_max_retries: int = 3
    rabbitmq_base_delay: float = 0.5
    rabbitmq_backoff_multiplier: float = 2.0

    algorithm: str = "HS256"
    jwt_secret: str = "dev-secret-key"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    cors_origins: list[str] = Field(default_factory=list)

    rate_limit_login: str = "5/minute"

    sentry_dsn: str | None = None
    debug: bool = False

    exchange_api_url: str = "https://api.exchangerate-api.com/v4/latest"
    exchange_api_urls: list[str] = Field(default_factory=lambda: [
        "https://api.exchangerate-api.com/v4/latest",
        "https://api.currencyapi.com/v3/latest",
        "https://api.fixer.io/latest",
    ])
    exchange_timeout: float = 5.0
    exchange_max_retries: int = 3
    exchange_backoff_base: float = 2.0

    @property
    def postgres_url(self) -> str:
        return (f"postgresql+asyncpg://{self.db_user}:{self.db_password}@"
                f"{self.db_host}:{self.db_port}/{self.db_name}")

    @property
    def sync_postgres_url(self) -> str:
        return (f"postgresql+psycopg2://{self.db_user}:{self.db_password}@"
                f"{self.db_host}:{self.db_port}/{self.db_name}")

    @property
    def postgres_replica_url(self) -> str:
        return (f"postgresql+asyncpg://{self.db_replica_user}:{self.db_replica_password}@"
                f"{self.db_replica_host}:{self.db_replica_port}/{self.db_replica_name}")

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="allow",
    )


app_settings = AppSettings()

uvicorn_options = {
    "host": app_settings.app_host,
    "port": app_settings.app_port,
    "workers": app_settings.cpu_count or multiprocessing.cpu_count(),
    "log_level": app_settings.log_level,
    "reload": app_settings.reload,
}
