"""Database session and connection management."""
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def validate_database_configuration(settings: Any) -> None:
    """Reject unsafe production database configuration before serving requests."""
    is_production = settings.app_env.strip().lower() in {"production", "prod"}
    url = settings.database_url
    if is_production and (not url or "CHANGE_ME" in url):
        raise RuntimeError(
            "DATABASE_URL must be configured with a PostgreSQL URL in production."
        )
    if is_production and not url.startswith("postgresql+asyncpg://"):
        raise RuntimeError(
            "Production DATABASE_URL must use the postgresql+asyncpg:// driver URL."
        )


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        settings = get_settings()
        url = settings.database_url
        validate_database_configuration(settings)
        if not url or "CHANGE_ME" in url:
            # SQLite is an explicit development convenience, never a production fallback.
            url = "sqlite+aiosqlite:///./sylvar_dev.db"
        connect_args: dict[str, Any] = {}
        engine_kwargs: dict[str, Any] = {
            "echo": False,
            "future": True,
        }
        if url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
        else:
            # Production PostgreSQL connection pooling settings (M-14)
            engine_kwargs["pool_pre_ping"] = True
            engine_kwargs["pool_recycle"] = 300
            engine_kwargs["pool_size"] = 10
            engine_kwargs["max_overflow"] = 20

        _engine = create_async_engine(
            url,
            connect_args=connect_args,
            **engine_kwargs,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        engine = get_engine()
        _session_factory = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return _session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a transactional AsyncSession."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            if session.in_transaction():
                await session.commit()
        except Exception:
            if session.in_transaction():
                await session.rollback()
            raise


@asynccontextmanager
async def transactional_session() -> AsyncGenerator[AsyncSession, None]:
    """Programmatic context manager for background or script operations."""
    factory = get_session_factory()
    async with factory() as session, session.begin():
        yield session
