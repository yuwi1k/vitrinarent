"""
Настройка БД: асинхронный стек для FastAPI (async_engine + AsyncSessionLocal).
PostgreSQL: креды из переменных окружения (.env).
"""
import os

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import NullPool

load_dotenv()

_db_user = os.getenv("POSTGRES_USER", "postgres")
_db_password = os.getenv("POSTGRES_PASSWORD", "postgres")
_db_name = os.getenv("POSTGRES_DB", "vitrina_db")
_db_host = os.getenv("POSTGRES_HOST", "localhost")
_db_port = os.getenv("POSTGRES_PORT", "5432")

SQLALCHEMY_DATABASE_URL_ASYNC = (
    f"postgresql+asyncpg://{_db_user}:{_db_password}@{_db_host}:{_db_port}/{_db_name}"
)
# Синхронный URL для Alembic (миграции работают через psycopg2)
SQLALCHEMY_DATABASE_URL_SYNC = (
    f"postgresql+psycopg2://{_db_user}:{_db_password}@{_db_host}:{_db_port}/{_db_name}"
)

# В тестах (TESTING=1) используем NullPool, чтобы избежать "another operation is in progress"
# при синхронном TestClient и общем пуле соединений.
_engine_kw = {"echo": False}
if os.getenv("TESTING", "").strip() in ("1", "true", "yes"):
    _engine_kw["poolclass"] = NullPool

async_engine = create_async_engine(SQLALCHEMY_DATABASE_URL_ASYNC, **_engine_kw)
AsyncSessionLocal = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# Базовый класс для моделей (общий для async и sync)
Base = declarative_base()


async def get_db():
    """Асинхронный генератор сессии для FastAPI (Depends(get_db))."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
