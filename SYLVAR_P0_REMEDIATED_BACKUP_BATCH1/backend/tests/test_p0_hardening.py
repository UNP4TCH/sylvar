"""Regression coverage for the P0 audit remediation changes."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import uuid

import pytest

from app.core.errors import ProblemException
from app.db import session as db_session_module
from app.modules.auth.pipeline import _set_tenant_local_context
from app.modules.engine_factual.verifier import run_async_factual_check


class _FakeSession:
    bind = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

    def __init__(self, fail: bool = False) -> None:
        self.execute = AsyncMock(side_effect=RuntimeError("database context failure") if fail else None)


def test_tenant_context_uses_parameterized_set_config_calls() -> None:
    session = _FakeSession()
    user_id, workspace_id, client_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    asyncio.run(_set_tenant_local_context(session, user_id, workspace_id, client_id))
    assert session.execute.await_count == 3
    first_call = session.execute.await_args_list[0]
    assert "set_config" in str(first_call.args[0])
    assert first_call.args[1]["setting_name"] == "app.current_user_id"
    assert first_call.args[1]["setting_value"] == str(user_id)
    assert session.execute.await_args_list[1].args[1]["setting_name"] == "app.current_workspace_id"
    assert session.execute.await_args_list[2].args[1]["setting_name"] == "app.current_client_id"


def test_tenant_context_explicitly_clears_unset_scope_values() -> None:
    session = _FakeSession()
    asyncio.run(_set_tenant_local_context(session, uuid.uuid4(), None, None))
    calls = session.execute.await_args_list
    assert len(calls) == 3
    assert calls[1].args[1]["setting_value"] == ""
    assert calls[2].args[1]["setting_value"] == ""


def test_tenant_context_fails_closed_when_postgres_rejects_context() -> None:
    session = _FakeSession(fail=True)
    with pytest.raises(ProblemException) as exc:
        asyncio.run(_set_tenant_local_context(session, uuid.uuid4(), None, None))
    assert exc.value.status == 503
    assert exc.value.code == "TENANT_CONTEXT_UNAVAILABLE"


def test_production_database_does_not_fall_back_to_sqlite() -> None:
    db_session_module._engine = None
    settings = SimpleNamespace(app_env="production", database_url=None)
    with patch.object(db_session_module, "get_settings", return_value=settings):
        with pytest.raises(RuntimeError, match="DATABASE_URL must be configured"):
            db_session_module.get_engine()
    db_session_module._engine = None


def test_production_database_requires_async_postgres_driver() -> None:
    db_session_module._engine = None
    settings = SimpleNamespace(app_env="production", database_url="sqlite+aiosqlite:///tmp/test.db")
    with patch.object(db_session_module, "get_settings", return_value=settings):
        with pytest.raises(RuntimeError, match=r"postgresql\+asyncpg"):
            db_session_module.get_engine()
    db_session_module._engine = None


def test_offline_factual_engine_cannot_authorize_compliance_pass() -> None:
    status, _findings, details = asyncio.run(
        run_async_factual_check(
            "Our product is an excellent solution.",
            [{"category": "FACT", "content": {"statement": "Made in India."}}],
            api_key=None,
        )
    )
    assert status == "FAIL"
    assert details["engine_mode"] == "deterministic_offline"
    assert details["authoritative"] is False

