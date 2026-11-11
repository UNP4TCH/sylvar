"""Contradiction Scanner & Human Resolution Router (Stage 3 Differentiator)."""
import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Path, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import ProblemException
from app.db.session import get_db
from app.models.document import CandidateStatus, ExtractedCandidate
from app.models.memory import BrandRule, BrandRuleRevision
from app.modules.auth.pipeline import SecurityContext, require_brand_manager, require_client_member
from app.modules.contradictions.scanner import scan_for_contradictions
from app.modules.contradictions.schemas import (
    ContradictionScanResponse,
    ResolutionRequest,
    ResolutionResponse,
)

logger = logging.getLogger("sylvar.contradictions")
router = APIRouter(tags=["Guideline Contradictions"])


@router.post(
    "/workspaces/{w_id}/clients/{c_id}/contradictions/scan",
    response_model=ContradictionScanResponse,
    summary="Scan client brand rules and candidates for contradictions (Stage 3 Differentiator)",
)
async def scan_brand_contradictions(
    w_id: uuid.UUID = Path(..., description="Workspace ID"),
    c_id: uuid.UUID = Path(..., description="Client Brand ID"),
    ctx: SecurityContext = Depends(require_client_member),
    db: AsyncSession = Depends(get_db),
) -> ContradictionScanResponse:
    # 1. Fetch all active brand rules with their latest revisions
    rule_stmt = (
        select(BrandRule)
        .where(BrandRule.workspace_id == w_id, BrandRule.client_id == c_id)
        .options(selectinload(BrandRule.revisions))
    )
    rules = (await db.execute(rule_stmt)).scalars().all()

    rules_payload = []
    for r in rules:
        if r.revisions:
            latest_rev = max(r.revisions, key=lambda x: x.revision_number)
            rules_payload.append(
                {
                    "rule_id": str(r.id),
                    "rule_code": r.rule_code,
                    "category": r.category.value if hasattr(r.category, "value") else str(r.category),
                    "content": latest_rev.content,
                }
            )

    # 2. Also fetch any pending candidate rules
    cand_stmt = select(ExtractedCandidate).where(
        ExtractedCandidate.workspace_id == w_id,
        ExtractedCandidate.client_id == c_id,
        ExtractedCandidate.review_status == CandidateStatus.PENDING_REVIEW.value,
    )
    candidates = (await db.execute(cand_stmt)).scalars().all()
    for c in candidates:
        rules_payload.append(
            {
                "rule_id": str(c.id),
                "rule_code": f"CANDIDATE-{c.category.value if hasattr(c.category, 'value') else str(c.category)}",
                "category": c.category.value if hasattr(c.category, "value") else str(c.category),
                "content": c.payload,
            }
        )

    # 3. Execute cross-rule contradiction scanner
    conflicts = scan_for_contradictions(rules_payload)
    has_critical = any(c.severity == "CRITICAL" for c in conflicts)

    return ContradictionScanResponse(
        workspace_id=w_id,
        client_id=c_id,
        rules_scanned_count=len(rules_payload),
        contradictions_count=len(conflicts),
        has_critical_conflicts=has_critical,
        contradictions=conflicts,
    )


@router.post(
    "/workspaces/{w_id}/clients/{c_id}/contradictions/{conflict_id}/resolve",
    response_model=ResolutionResponse,
    summary="Human resolution of guideline contradiction (Stage 3 Differentiator)",
)
async def resolve_brand_contradiction(
    payload: ResolutionRequest,
    w_id: uuid.UUID = Path(..., description="Workspace ID"),
    c_id: uuid.UUID = Path(..., description="Client Brand ID"),
    conflict_id: str = Path(..., description="Conflict ID"),
    ctx: SecurityContext = Depends(require_brand_manager),
    db: AsyncSession = Depends(get_db),
) -> ResolutionResponse:
    # 1. Re-scan to find matching conflict
    scan_res = await scan_brand_contradictions(w_id, c_id, ctx, db)
    matching = next((c for c in scan_res.contradictions if c.conflict_id == conflict_id), None)
    if not matching:
        raise ProblemException(
            status=status.HTTP_404_NOT_FOUND,
            code="CONFLICT_NOT_FOUND",
            title="Conflict Not Found",
            detail=f"Conflict ID '{conflict_id}' was not found in active guidelines.",
        )

    rule_a_id = uuid.UUID(matching.rule_a.rule_id)
    rule_b_id = uuid.UUID(matching.rule_b.rule_id)

    rule_a = await db.get(BrandRule, rule_a_id)
    rule_b = await db.get(BrandRule, rule_b_id)

    retained_id = None
    deprecated_id = None

    if payload.resolution_action == "KEEP_A":
        retained_id = str(rule_a_id)
        deprecated_id = str(rule_b_id)
        if rule_b:
            await db.delete(rule_b)
            await db.flush()
        else:
            cand_b = await db.get(ExtractedCandidate, rule_b_id)
            if cand_b:
                cand_b.review_status = CandidateStatus.REJECTED.value
                await db.flush()
        msg = f"Rule [{matching.rule_a.rule_code}] retained. Conflicting rule [{matching.rule_b.rule_code}] deprecated per Brand Manager decision."

    elif payload.resolution_action == "KEEP_B":
        retained_id = str(rule_b_id)
        deprecated_id = str(rule_a_id)
        if rule_a:
            await db.delete(rule_a)
            await db.flush()
        else:
            cand_a = await db.get(ExtractedCandidate, rule_a_id)
            if cand_a:
                cand_a.review_status = CandidateStatus.REJECTED.value
                await db.flush()
        msg = f"Rule [{matching.rule_b.rule_code}] retained. Conflicting rule [{matching.rule_a.rule_code}] deprecated per Brand Manager decision."

    elif payload.resolution_action == "MANUAL_OVERRIDE":
        if not payload.custom_statement or not payload.custom_statement.strip():
            raise ProblemException(
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                code="CUSTOM_STATEMENT_REQUIRED",
                title="Custom Statement Required",
                detail="A non-empty custom_statement is required for MANUAL_OVERRIDE resolution.",
            )
        retained_id = str(rule_a_id)
        deprecated_id = str(rule_b_id)

        # Update Rule A with human unified revision
        if rule_a:
            rev_stmt = select(BrandRuleRevision).where(BrandRuleRevision.rule_id == rule_a_id)
            revs = (await db.execute(rev_stmt)).scalars().all()
            next_rev = (max(r.revision_number for r in revs) + 1) if revs else 1
            new_rev = BrandRuleRevision(
                rule_id=rule_a.id,
                revision_number=next_rev,
                content={"statement": payload.custom_statement, "unified_resolution": True},
                rationale=f"Human contradiction resolution: {payload.resolution_notes}",
            )
            db.add(new_rev)
            await db.flush()

        if rule_b:
            await db.delete(rule_b)
            await db.flush()

        msg = f"Contradiction resolved with human unified statement. Rule [{matching.rule_a.rule_code}] updated, [{matching.rule_b.rule_code}] merged."

    return ResolutionResponse(
        conflict_id=conflict_id,
        status="RESOLVED",
        resolution_action=payload.resolution_action,
        resolution_notes=payload.resolution_notes,
        retained_rule_id=retained_id,
        deprecated_rule_id=deprecated_id,
        message=msg,
    )

