"""Living Brand Memory approval, versioning, and snapshot compiler API routes (Groups 9 & 10)."""
import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Path, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ProblemException
from app.db.session import get_db
from app.models.client import ClientBrand
from app.models.document import CandidateStatus, ExtractedCandidate, RuleCategory
from app.models.memory import (
    BrandMemorySnapshot,
    BrandMemoryVersion,
    BrandRule,
    BrandRuleRevision,
    MemoryVersionStatus,
    brand_memory_version_rules,
)
from app.modules.auth.pipeline import SecurityContext, require_brand_manager, require_client_member

router = APIRouter(tags=["Living Brand Memory"])


class ApproveCandidatesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_ids: list[uuid.UUID] = Field(..., min_length=1)


class ApprovedRuleItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rule_id: uuid.UUID
    revision_id: uuid.UUID
    rule_code: str
    category: str


class ApproveCandidatesResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    approved_count: int
    rules: list[ApprovedRuleItem]


class ActivateMemoryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version_tag: str = Field(..., min_length=2, max_length=50)
    change_summary: str | None = Field(default=None, max_length=1000)


class MemoryActivationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    memory_version_id: uuid.UUID
    snapshot_id: uuid.UUID
    snapshot_hash: str
    version_number: int
    version_tag: str
    rule_count: int


@router.post(
    "/workspaces/{w_id}/clients/{c_id}/knowledge/approve",
    response_model=ApproveCandidatesResponse,
    summary="Approve candidate rules into authoritative brand rules (Group 9)",
)
async def approve_candidates(
    payload: ApproveCandidatesRequest,
    w_id: uuid.UUID = Path(..., description="Workspace ID"),
    c_id: uuid.UUID = Path(..., description="Client Brand ID"),
    ctx: SecurityContext = Depends(require_brand_manager),
    db: AsyncSession = Depends(get_db),
) -> ApproveCandidatesResponse:
    approved_items: list[ApprovedRuleItem] = []

    for cand_id in payload.candidate_ids:
        cand = await db.get(ExtractedCandidate, cand_id)
        if not cand or cand.workspace_id != w_id or cand.client_id != c_id:
            continue

        # Resolves M-07: Idempotency and status check
        if cand.review_status not in (
            CandidateStatus.PENDING_REVIEW.value,
            CandidateStatus.MODIFIED_APPROVED.value,
        ):
            continue

        # Resolves M-07: Validate rule category and payload structure
        cat = cand.category.upper().strip()
        valid_cats = {
            RuleCategory.TERMINOLOGY.value,
            RuleCategory.FACT.value,
            RuleCategory.COLOR.value,
            RuleCategory.VOICE.value,
        }
        if cat not in valid_cats:
            continue

        if not isinstance(cand.payload, dict) or not cand.payload:
            continue

        # Generate unique rule code
        rule_code = f"RULE-{cat[:4]}-{str(cand.id)[:8].upper()}"

        # 1. Create or resolve BrandRule
        rule = BrandRule(
            workspace_id=w_id,
            client_id=c_id,
            rule_code=rule_code,
            category=cand.category,
        )
        db.add(rule)
        await db.flush()

        # 2. Create immutable Revision 1
        rev = BrandRuleRevision(
            rule_id=rule.id,
            revision_number=1,
            content=cand.payload,
            rationale="Approved from candidate rule extraction",
        )
        db.add(rev)
        await db.flush()

        # 3. Update candidate status
        cand.review_status = CandidateStatus.APPROVED.value
        cand.updated_at = datetime.now(UTC)

        approved_items.append(
            ApprovedRuleItem(
                rule_id=rule.id,
                revision_id=rev.id,
                rule_code=rule.rule_code,
                category=rule.category,
            )
        )

    await db.flush()
    return ApproveCandidatesResponse(
        approved_count=len(approved_items),
        rules=approved_items,
    )


@router.post(
    "/workspaces/{w_id}/clients/{c_id}/memory/activate",
    response_model=MemoryActivationResponse,
    summary="Publish memory release and compile immutable JSONB snapshot (Group 10)",
)
async def activate_memory(
    payload: ActivateMemoryRequest,
    w_id: uuid.UUID = Path(..., description="Workspace ID"),
    c_id: uuid.UUID = Path(..., description="Client Brand ID"),
    ctx: SecurityContext = Depends(require_brand_manager),
    db: AsyncSession = Depends(get_db),
) -> MemoryActivationResponse:
    # 0. Acquire row lock on ClientBrand to serialize concurrent activations (Resolves M-08)
    brand_stmt = (
        select(ClientBrand)
        .where(
            ClientBrand.id == c_id,
            ClientBrand.workspace_id == w_id,
        )
        .with_for_update()
    )
    brand = (await db.execute(brand_stmt)).scalar_one_or_none()
    if not brand:
        raise ProblemException(
            status=status.HTTP_404_NOT_FOUND,
            code="CLIENT_NOT_FOUND",
            title="Not Found",
            detail="Client brand not found.",
        )

    # 1. Fetch all brand rules and their latest revisions for this client
    rules_stmt = select(BrandRule).where(
        BrandRule.workspace_id == w_id,
        BrandRule.client_id == c_id,
    )
    rules = (await db.execute(rules_stmt)).scalars().all()
    if not rules:
        raise ProblemException(
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="NO_APPROVED_RULES",
            title="Unprocessable Entity",
            detail="Cannot publish a memory version with zero approved rules.",
        )

    # 2. Get latest revision for each rule
    revisions: list[BrandRuleRevision] = []
    snapshot_rules_data: list[dict[str, Any]] = []

    for rule in rules:
        rev_stmt = (
            select(BrandRuleRevision)
            .where(BrandRuleRevision.rule_id == rule.id)
            .order_by(desc(BrandRuleRevision.revision_number))
            .limit(1)
        )
        rev = (await db.execute(rev_stmt)).scalar_one_or_none()
        if rev:
            revisions.append(rev)
            snapshot_rules_data.append(
                {
                    "rule_id": str(rule.id),
                    "rule_code": rule.rule_code,
                    "category": rule.category,
                    "revision_id": str(rev.id),
                    "revision_number": rev.revision_number,
                    "content": rev.content,
                }
            )

    # 3. Determine next version number
    v_num_stmt = select(func.coalesce(func.max(BrandMemoryVersion.version_number), 0)).where(
        BrandMemoryVersion.workspace_id == w_id,
        BrandMemoryVersion.client_id == c_id,
    )
    max_v = (await db.execute(v_num_stmt)).scalar() or 0
    next_v = max_v + 1

    # 4. Supersede existing active versions
    existing_active_stmt = select(BrandMemoryVersion).where(
        BrandMemoryVersion.workspace_id == w_id,
        BrandMemoryVersion.client_id == c_id,
        BrandMemoryVersion.status == MemoryVersionStatus.ACTIVE.value,
    )
    existing_actives = (await db.execute(existing_active_stmt)).scalars().all()
    for active_v in existing_actives:
        active_v.status = MemoryVersionStatus.SUPERSEDED.value

    # 5. Resolve version tag and create new BrandMemoryVersion
    # Prevent duplicate version_tag conflict within workspace and client (Batch 2B Task 3)
    version_tag = payload.version_tag.strip() if payload.version_tag else f"v{next_v}.0.0"
    existing_tag_stmt = select(BrandMemoryVersion).where(
        BrandMemoryVersion.workspace_id == w_id,
        BrandMemoryVersion.client_id == c_id,
        BrandMemoryVersion.version_tag == version_tag,
    )
    if (await db.execute(existing_tag_stmt)).scalar_one_or_none():
        version_tag = f"{version_tag}-v{next_v}"

    mem_version = BrandMemoryVersion(
        workspace_id=w_id,
        client_id=c_id,
        version_number=next_v,
        version_tag=version_tag,
        status=MemoryVersionStatus.ACTIVE.value,
        change_summary=payload.change_summary,
    )
    db.add(mem_version)
    await db.flush()

    # Link revisions in association table
    for r in revisions:
        await db.execute(
            brand_memory_version_rules.insert().values(
                memory_version_id=mem_version.id,
                rule_revision_id=r.id,
            )
        )

    # 6. Compile materialized snapshot data & compute deterministic SHA-256 hash
    snapshot_payload = {
        "workspace_id": str(w_id),
        "client_id": str(c_id),
        "version_tag": version_tag,
        "version_number": next_v,
        "rules": sorted(snapshot_rules_data, key=lambda x: str(x["rule_code"])),
    }
    canonical_json = json.dumps(snapshot_payload, sort_keys=True, separators=(",", ":"))
    snapshot_hash = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

    snapshot = BrandMemorySnapshot(
        workspace_id=w_id,
        client_id=c_id,
        memory_version_id=mem_version.id,
        snapshot_hash=snapshot_hash,
        snapshot_data=snapshot_payload,
    )
    db.add(snapshot)
    await db.flush()

    # 7. Update client brand active pointer (TASK-020)
    brand.active_memory_version_id = mem_version.id
    await db.flush()

    return MemoryActivationResponse(
        memory_version_id=mem_version.id,
        snapshot_id=snapshot.id,
        snapshot_hash=snapshot_hash,
        version_number=next_v,
        version_tag=mem_version.version_tag,
        rule_count=len(snapshot_rules_data),
    )


@router.get(
    "/workspaces/{w_id}/clients/{c_id}/memory/active",
    summary="Retrieve currently active brand memory snapshot",
)
async def get_active_memory(
    w_id: uuid.UUID = Path(..., description="Workspace ID"),
    c_id: uuid.UUID = Path(..., description="Client Brand ID"),
    ctx: SecurityContext = Depends(require_client_member),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    brand = await db.get(ClientBrand, c_id)
    if not brand or not brand.active_memory_version_id:
        return {"active": False, "version": None, "snapshot": None}

    mem_version = await db.get(BrandMemoryVersion, brand.active_memory_version_id)
    if not mem_version:
        return {"active": False, "version": None, "snapshot": None}

    snap_stmt = select(BrandMemorySnapshot).where(
        BrandMemorySnapshot.memory_version_id == mem_version.id
    )
    snapshot = (await db.execute(snap_stmt)).scalar_one_or_none()

    return {
        "active": True,
        "version": {
            "version_id": str(mem_version.id),
            "version_number": mem_version.version_number,
            "version_tag": mem_version.version_tag,
            "status": mem_version.status,
            "change_summary": mem_version.change_summary,
        },
        "snapshot": {
            "snapshot_id": str(snapshot.id) if snapshot else None,
            "snapshot_hash": snapshot.snapshot_hash if snapshot else None,
            "data": snapshot.snapshot_data if snapshot else None,
        },
    }
