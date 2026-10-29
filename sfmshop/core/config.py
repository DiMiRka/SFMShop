import multiprocessing
from typing import Any

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
    mongo_db: str = "sfmshop"
    event_log_ttl_days: int = 90

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
    rate_limit_storage_uri: str = "memory://"

    metrics_port: int | None = 9100

    sentry_dsn: str | None = None
    debug: bool = False

    llm_provider: str = "anthropic"
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    llm_model: str | None = None
    llm_timeout: float = 30.0
    llm_max_retries: int = 3
    llm_max_tool_steps: int = 5
    llm_max_tokens: int = 4096
    rate_limit_assistant: str = "10/minute"

    embedding_provider: str = "openai"
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    embedding_batch_size: int = 100
    embedding_usd_per_million_tokens: float = 0.02
    embedding_timeout: float = 30.0
    embedding_max_retries: int = 3
    embedding_query_cache_ttl: int = 86400
    semantic_min_similarity: float = 0.3
    rate_limit_semantic_search: str = "30/minute"

    payment_service_url: str | None = None
    payment_service_token: str = ""
    payment_timeout: float = 5.0
    payment_connect_timeout: float = 2.0
    payment_max_retries: int = 3

    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_start_tls: bool = True
    smtp_timeout: float = 10.0
    smtp_from: str = "SFMShop <noreply@sfmshop.local>"

    marketplace_timeout: float = 30.0
    marketplace_connect_timeout: float = 5.0
    marketplace_max_retries: int = 3
    marketplace_sync_interval: float = 300.0
    marketplace_orders_lookback_hours: int = 24
    marketplace_orders_overlap_minutes: int = 60
    ozon_client_id: str | None = None
    ozon_api_key: str | None = None
    ozon_base_url: str = "https://api-seller.ozon.ru"
    ozon_warehouse_id: int | None = None
    wb_api_token: str | None = None
    wb_prices_base_url: str = "https://discounts-prices-api.wildberries.ru"
    wb_marketplace_base_url: str = "https://marketplace-api.wildberries.ru"
    wb_warehouse_id: int | None = None

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

uvicorn_options: dict[str, Any] = {
    "host": app_settings.app_host,
    "port": app_settings.app_port,
    "workers": app_settings.cpu_count or multiprocessing.cpu_count(),
    "log_level": app_settings.log_level,
    "reload": app_settings.reload,
}
