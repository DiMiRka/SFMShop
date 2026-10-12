from pydantic_settings import BaseSettings, SettingsConfigDict


class PaymentSettings(BaseSettings):
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "payment_db"
    db_user: str = "postgres"
    db_password: str = "password"

    service_token: str = ""
    metrics_port: int | None = 9101

    model_config = SettingsConfigDict(env_prefix="PAYMENT_", env_file=".env", extra="ignore")

    @property
    def postgres_url(self) -> str:
        return (f"postgresql+asyncpg://{self.db_user}:{self.db_password}@"
                f"{self.db_host}:{self.db_port}/{self.db_name}")

    @property
    def sync_postgres_url(self) -> str:
        return (f"postgresql+psycopg2://{self.db_user}:{self.db_password}@"
                f"{self.db_host}:{self.db_port}/{self.db_name}")


settings = PaymentSettings()
