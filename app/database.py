"""
Настройка БД: асинхронный стек для FastAPI (async_engine + AsyncSessionLocal),
синхронный engine и SessionLocal — только для SQLAdmin.
"""
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# URL для асинхронной работы (FastAPI, роуты)
SQLALCHEMY_DATABASE_URL_ASYNC = "sqlite+aiosqlite:///./vitrina.db"

# URL для синхронной работы (SQLAdmin и Alembic)
SQLALCHEMY_DATABASE_URL_SYNC = "sqlite:///./vitrina.db"

# Асинхронный движок и фабрика сессий для приложения
async_engine = create_async_engine(
    SQLALCHEMY_DATABASE_URL_ASYNC,
    connect_args={"check_same_thread": False},
    echo=False,
)
AsyncSessionLocal = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# Синхронный движок и фабрика сессий только для SQLAdmin
engine = create_engine(
    SQLALCHEMY_DATABASE_URL_SYNC,
    connect_args={"check_same_thread": False},
)
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
