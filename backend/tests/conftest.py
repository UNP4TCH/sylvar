"""Pytest configuration and shared fixtures for SYLVAR backend test suites."""
from collections.abc import AsyncGenerator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from tests.db_helpers import TestSessionLocal, init_test_db, reset_test_db


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provides an isolated async SQLite session with all database tables initialized."""
    await reset_test_db()
    async with TestSessionLocal() as session:
        yield session
        await session.rollback()

