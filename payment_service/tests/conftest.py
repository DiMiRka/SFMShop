import os

os.environ.setdefault("PAYMENT_DB_NAME", "payment_test")
os.environ["PAYMENT_SERVICE_TOKEN"] = "test-token"

from contextlib import asynccontextmanager  # noqa: E402
from pathlib import Path  # noqa: E402

import httpx  # noqa: E402
import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from payment.core.config import settings  # noqa: E402
from payment.database.connection import get_session  # noqa: E402
from payment.main import app  # noqa: E402
from payment.repository import PaymentRepository  # noqa: E402
from payment.service import PaymentService  # noqa: E402


TOKEN = {"X-Service-Token": "test-token"}
ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


def alembic_config() -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(ALEMBIC_INI.parent / "alembic"))
    return config


def ensure_database():
    admin_url = settings.sync_postgres_url.rsplit("/", 1)[0] + "/postgres"
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as connection:
            exists = connection.execute(text("SELECT 1 FROM pg_database WHERE datname = :name"),
                                        {"name": settings.db_name}).scalar()
            if not exists:
                connection.execute(text(f'CREATE DATABASE "{settings.db_name}"'))
    finally:
        admin.dispose()


@pytest.fixture(scope="session")
def sync_engine():
    ensure_database()
    engine = create_engine(settings.sync_postgres_url)
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    command.upgrade(alembic_config(), "head")
    yield engine
    engine.dispose()


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def session_factory(sync_engine):
    with sync_engine.begin() as connection:
        connection.execute(text("TRUNCATE wallet_transactions, payments, wallets RESTART IDENTITY CASCADE"))

    engine = create_async_engine(settings.postgres_url, poolclass=NullPool)
    yield async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    await engine.dispose()


@pytest.fixture
def service_in(session_factory):
    @asynccontextmanager
    async def open_service():
        async with session_factory() as session:
            yield PaymentService(PaymentRepository(session))

    return open_service


@pytest.fixture
async def client(session_factory):
    async def override_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://payment", headers=TOKEN) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def db(sync_engine):
    def query(sql, **params):
        with sync_engine.connect() as connection:
            return connection.execute(text(sql), params).all()

    return query
