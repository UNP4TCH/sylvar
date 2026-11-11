from typing import Any

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db

router = APIRouter(tags=["health"])


class LivenessResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str


class ReadinessResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str
    database: str


@router.get("/health", response_model=LivenessResponse)
async def liveness() -> LivenessResponse:
    """Public process liveness only (API_DESIGN Group 20). No DB or auth dependency."""
    return LivenessResponse(status="alive")


@router.get("/health/ready", response_model=ReadinessResponse)
async def readiness(db: AsyncSession = Depends(get_db)) -> Any:
    """Readiness probe: validates database pool connectivity before serving traffic."""
    try:
        await db.execute(text("SELECT 1"))
        return ReadinessResponse(status="ready", database="connected")
    except Exception:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            media_type="application/problem+json",
            content={
                "type": "about:blank#DATABASE_UNAVAILABLE",
                "title": "Service Unavailable",
                "status": 503,
                "detail": "Database connectivity check failed.",
                "code": "DATABASE_UNAVAILABLE",
            },
        )
