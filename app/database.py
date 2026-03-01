"""
Настройка БД: асинхронный стек для FastAPI (async_engine + AsyncSessionLocal),
синхронный engine и SessionLocal — только для SQLAdmin.
PostgreSQL: креды из переменных окружения (.env).
"""
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

load_dotenv()

_db_user = os.getenv("POSTGRES_USER", "postgres")
_db_password = os.getenv("POSTGRES_PASSWORD", "postgres")
_db_name = os.getenv("POSTGRES_DB", "vitrina_db")
_db_host = os.getenv("POSTGRES_HOST", "localhost")
_db_port = os.getenv("POSTGRES_PORT", "5432")

# URL для асинхронной работы (FastAPI, роуты)
SQLALCHEMY_DATABASE_URL_ASYNC = (
    f"postgresql+asyncpg://{_db_user}:{_db_password}@{_db_host}:{_db_port}/{_db_name}"
)

# URL для синхронной работы (SQLAdmin и Alembic)
SQLALCHEMY_DATABASE_URL_SYNC = (
    f"postgresql+psycopg2://{_db_user}:{_db_password}@{_db_host}:{_db_port}/{_db_name}"
)

# Асинхронный движок и фабрика сессий для приложения
async_engine = create_async_engine(
    SQLALCHEMY_DATABASE_URL_ASYNC,
    echo=False,
)
AsyncSessionLocal = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# Синхронный движок и фабрика сессий только для SQLAdmin
engine = create_engine(SQLALCHEMY_DATABASE_URL_SYNC)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Базовый класс для моделей (общий для async и sync)
Base = declarative_base()


async def get_db():
    """Асинхронный генератор сессии для FastAPI (Depends(get_db))."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
