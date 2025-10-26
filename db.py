"""Утилиты для работы с базой данных проекта Aura."""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

from sqlalchemy.ext.asyncio import (
    AsyncAttrs,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.sql.schema import MetaData
from sqlalchemy.orm import DeclarativeBase

__all__ = [
    "DATABASE_URL",
    "engine",
    "SessionLocal",
    "Base",
    "init_db",
    "session_scope",
]

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///aura.db")

engine: AsyncEngine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
)
SessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)


class Base(AsyncAttrs, DeclarativeBase):
    """Общий базовый класс для ORM-моделей."""


async def init_db(metadata: Optional[MetaData] = None) -> None:
    """Создаёт таблицы в базе данных, если их ещё нет."""

    async with engine.begin() as conn:
        await conn.run_sync((metadata or Base.metadata).create_all)


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Асинхронный контекст для безопасной работы с сессией."""

    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
