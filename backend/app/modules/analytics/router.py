"""Longitudinal Insights & Analytics API Router (Stage 3 Differentiator)."""
import logging
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.audit import AuditFinding, AuditRun, CorrectionSuggestion
from app.modules.analytics.calculator import compute_longitudinal_insights
from app.modules.analytics.schemas import LongitudinalInsightsResponse
from app.modules.auth.pipeline import SecurityContext, require_client_member

logger = logging.getLogger("sylvar.analytics")
router = APIRouter(tags=["Longitudinal Insights & Analytics"])


@router.get(
    "/workspaces/{w_id}/clients/{c_id}/analytics/insights",
    response_model=LongitudinalInsightsResponse,
    summary="Get tenant-scoped longitudinal brand compliance insights (Stage 3 Differentiator)",
)
async def get_longitudinal_insights(
    w_id: uuid.UUID = Path(..., description="Workspace ID"),
    c_id: uuid.UUID = Path(..., description="Client Brand ID"),
    days: int = Query(default=30, ge=1, le=365, description="Lookback window in days"),
    ctx: SecurityContext = Depends(require_client_member),
    db: AsyncSession = Depends(get_db),
) -> LongitudinalInsightsResponse:
    since = datetime.now(UTC) - timedelta(days=days)

    # 1. Fetch tenant-scoped audit runs
    run_stmt = select(AuditRun).where(
        AuditRun.workspace_id == w_id,
        AuditRun.client_id == c_id,
        AuditRun.created_at >= since,
    )
    audit_runs = (await db.execute(run_stmt)).scalars().all()
    run_ids = [r.id for r in audit_runs]

    # 2. Fetch corresponding findings
    findings = []
    if run_ids:
        finding_stmt = select(AuditFinding).where(
            AuditFinding.workspace_id == w_id,
            AuditFinding.client_id == c_id,
            AuditFinding.audit_run_id.in_(run_ids),
        )
        findings = (await db.execute(finding_stmt)).scalars().all()

    # 3. Fetch corresponding suggestions
    suggestions = []
    if run_ids:
        sugg_stmt = select(CorrectionSuggestion).where(
            CorrectionSuggestion.workspace_id == w_id,
            CorrectionSuggestion.client_id == c_id,
            CorrectionSuggestion.audit_run_id.in_(run_ids),
        )
        suggestions = (await db.execute(sugg_stmt)).scalars().all()

    # 4. Compute privacy-conscious insights
    return compute_longitudinal_insights(
        workspace_id=w_id,
        client_id=c_id,
        period_days=days,
        audit_runs=audit_runs,
        findings=findings,
        suggestions=suggestions,
    )

