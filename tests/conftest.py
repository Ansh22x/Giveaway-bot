import os
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import StaticPool

# Set test environment variables before importing app modules
os.environ["BOT_TOKEN"] = "123456789:TEST_MOCK_TOKEN"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["WEBHOOK_SECRET"] = "test_webhook_secret_key"
os.environ["WEBHOOK_BASE_URL"] = "https://test.example.com"
os.environ["ADMIN_CHAT_ID"] = "123456789"
os.environ["LOG_LEVEL"] = "DEBUG"
os.environ["DATABASE_POOL_SIZE"] = "1"

from app.database import Base
from app.models.models import User, Giveaway, Entry, PendingAction, GiveawayAdmin, AuditLog, ProcessedUpdate


@pytest_asyncio.fixture(scope="function")
async def test_engine():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(test_engine):
    async_session = async_sessionmaker(
        bind=test_engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    async with async_session() as session:
        yield session
