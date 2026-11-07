"""Content Asset and Audit Governance API routes (Domain E & F)."""
import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Path, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import ProblemException
from app.db.session import get_db
from app.models.audit import AuditFinding, AuditRun, CorrectionSuggestion
from app.models.client import ClientBrand
from app.models.content import AssetVersion, ContentAsset, ContentType
from app.models.memory import BrandMemorySnapshot
from app.modules.auth.pipeline import SecurityContext, require_client_member
from app.modules.orchestrator.runner import execute_audit
from app.modules.remediation.engine import apply_surgical_corrections, create_remediated_version

router = APIRouter(tags=["Content Governance & Audits"])


class AssetCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(..., min_length=2, max_length=255)
    content_type: ContentType = ContentType.TEXT
    text_content: str | None = Field(default=None)


class AssetVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    version_id: uuid.UUID
    asset_id: uuid.UUID
    version_number: int
    text_content: str | None = None
    sha256_hash: str
    created_from_correction_id: uuid.UUID | None = None
    created_at: datetime


class AssetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    asset_id: uuid.UUID
    workspace_id: uuid.UUID
    client_id: uuid.UUID
    title: str
    content_type: str
    latest_version: AssetVersionResponse | None = None
    created_at: datetime


class SuggestionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    suggestion_id: uuid.UUID
    finding_id: uuid.UUID
    original_text: str
    suggested_text: str
    rationale: str
    applied_at: datetime | None = None


class FindingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    finding_id: uuid.UUID
    rule_id: uuid.UUID | None = None
    rule_code: str | None = None
    severity: str
    message: str
    location_start: int | None = None
    location_end: int | None = None
    snippet: str | None = None
    evidence: dict[str, Any]
    suggestions: list[SuggestionResponse] = []


class CheckResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    check_id: uuid.UUID
    engine_type: str
    status: str
    execution_time_ms: int
    summary_details: dict[str, Any]


class AuditRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    audit_run_id: uuid.UUID
    asset_id: uuid.UUID
    asset_version_id: uuid.UUID
    snapshot_id: uuid.UUID
    status: str
    overall_verdict: str | None = None
    created_at: datetime
    completed_at: datetime | None = None
    checks: list[CheckResponse] = []
    findings: list[FindingResponse] = []


class RemediationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suggestion_ids: list[uuid.UUID] = Field(..., min_length=1)


# -----------------------------------------------------------------------------
# Asset Endpoints
# -----------------------------------------------------------------------------
@router.post(
    "/workspaces/{w_id}/clients/{c_id}/assets",
    response_model=AssetResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create content asset and initial version (Group 11)",
)
async def create_asset(
    payload: AssetCreateRequest,
    w_id: uuid.UUID = Path(..., description="Workspace ID"),
    c_id: uuid.UUID = Path(..., description="Client Brand ID"),
    ctx: SecurityContext = Depends(require_client_member),
    db: AsyncSession = Depends(get_db),
) -> AssetResponse:
    if payload.content_type != ContentType.TEXT:
        raise ProblemException(
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="CONTENT_TYPE_NOT_SUPPORTED",
            title="Unsupported Content Type",
            detail="The current MVP supports TEXT assets only. IMAGE and HYBRID assets are disabled until visual upload and audit are implemented.",
        )
    if not payload.text_content or not payload.text_content.strip():
        raise ProblemException(
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="TEXT_CONTENT_REQUIRED",
            title="Text Content Required",
            detail="A non-empty text body is required for a TEXT asset.",
        )

    asset = ContentAsset(
        workspace_id=w_id,
        client_id=c_id,
        title=payload.title,
        content_type=payload.content_type.value,
        created_by_user_id=ctx.user_id,
    )
    db.add(asset)
    await db.flush()

    raw_text = payload.text_content or ""
    sha256 = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()

    v1 = AssetVersion(
        workspace_id=w_id,
        client_id=c_id,
        asset_id=asset.id,
        version_number=1,
        text_content=payload.text_content,
        sha256_hash=sha256,
        created_by_user_id=ctx.user_id,
    )
    db.add(v1)
    await db.flush()

    return AssetResponse(
        asset_id=asset.id,
        workspace_id=w_id,
        client_id=c_id,
        title=asset.title,
        content_type=asset.content_type,
        latest_version=AssetVersionResponse(
            version_id=v1.id,
            asset_id=v1.asset_id,
            version_number=v1.version_number,
            text_content=v1.text_content,
            sha256_hash=v1.sha256_hash,
            created_from_correction_id=v1.created_from_correction_id,
            created_at=v1.created_at,
        ),
        created_at=asset.created_at,
    )


@router.get(
    "/workspaces/{w_id}/clients/{c_id}/assets/{a_id}",
    response_model=AssetResponse,
    summary="Get content asset with latest version",
)
async def get_asset(
    w_id: uuid.UUID = Path(..., description="Workspace ID"),
    c_id: uuid.UUID = Path(..., description="Client Brand ID"),
    a_id: uuid.UUID = Path(..., description="Asset ID"),
    ctx: SecurityContext = Depends(require_client_member),
    db: AsyncSession = Depends(get_db),
) -> AssetResponse:
    stmt = (
        select(ContentAsset)
        .where(
            ContentAsset.id == a_id,
            ContentAsset.workspace_id == w_id,
            ContentAsset.client_id == c_id,
        )
        .options(selectinload(ContentAsset.versions))
    )
    asset = (await db.execute(stmt)).scalar_one_or_none()
    if not asset:
        raise ProblemException(
            status=status.HTTP_404_NOT_FOUND,
            code="ASSET_NOT_FOUND",
            title="Not Found",
            detail="Content asset not found.",
        )

    latest_v = max(asset.versions, key=lambda v: v.version_number) if asset.versions else None

    return AssetResponse(
        asset_id=asset.id,
        workspace_id=w_id,
        client_id=c_id,
        title=asset.title,
        content_type=asset.content_type,
        latest_version=AssetVersionResponse(
            version_id=latest_v.id,
            asset_id=latest_v.asset_id,
            version_number=latest_v.version_number,
            text_content=latest_v.text_content,
            sha256_hash=latest_v.sha256_hash,
            created_from_correction_id=latest_v.created_from_correction_id,
            created_at=latest_v.created_at,
        )
        if latest_v
        else None,
        created_at=asset.created_at,
    )


# -----------------------------------------------------------------------------
# Audit Execution Endpoints
# -----------------------------------------------------------------------------
@router.post(
    "/workspaces/{w_id}/clients/{c_id}/assets/{a_id}/versions/{v_id}/audit",
    response_model=AuditRunResponse,
    summary="Trigger pre-publication governance audit (TASK-021)",
)
async def trigger_audit(
    w_id: uuid.UUID = Path(..., description="Workspace ID"),
    c_id: uuid.UUID = Path(..., description="Client Brand ID"),
    a_id: uuid.UUID = Path(..., description="Asset ID"),
    v_id: uuid.UUID = Path(..., description="Asset Version ID"),
    ctx: SecurityContext = Depends(require_client_member),
    db: AsyncSession = Depends(get_db),
) -> AuditRunResponse:
    # 1. Fetch and validate the parent asset before resolving its version.
    asset_stmt = select(ContentAsset).where(
        ContentAsset.id == a_id,
        ContentAsset.workspace_id == w_id,
        ContentAsset.client_id == c_id,
    )
    asset = (await db.execute(asset_stmt)).scalar_one_or_none()
    if not asset:
        raise ProblemException(
            status=status.HTTP_404_NOT_FOUND,
            code="ASSET_NOT_FOUND",
            title="Not Found",
            detail="Content asset not found.",
        )
    if asset.content_type != ContentType.TEXT.value:
        raise ProblemException(
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="CONTENT_TYPE_NOT_SUPPORTED",
            title="Unsupported Content Type",
            detail="Only TEXT assets can be audited in the current MVP. IMAGE and HYBRID audits are disabled.",
        )

    # 2. Fetch asset version
    v_stmt = select(AssetVersion).where(
        AssetVersion.id == v_id,
        AssetVersion.asset_id == a_id,
        AssetVersion.workspace_id == w_id,
        AssetVersion.client_id == c_id,
    )
    version = (await db.execute(v_stmt)).scalar_one_or_none()
    if not version:
        raise ProblemException(
            status=status.HTTP_404_NOT_FOUND,
            code="VERSION_NOT_FOUND",
            title="Not Found",
            detail="Asset version not found.",
        )

    # 3. Fetch active memory snapshot for brand
    brand = await db.get(ClientBrand, c_id)
    if not brand or not brand.active_memory_version_id:
        raise ProblemException(
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="NO_ACTIVE_MEMORY",
            title="Unprocessable Entity",
            detail="Cannot audit content: No active brand memory version is configured for this client.",
        )

    snap_stmt = select(BrandMemorySnapshot).where(
        BrandMemorySnapshot.memory_version_id == brand.active_memory_version_id
    )
    snapshot = (await db.execute(snap_stmt)).scalar_one_or_none()
    if not snapshot:
        raise ProblemException(
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="SNAPSHOT_NOT_FOUND",
            title="Unprocessable Entity",
            detail="Active brand memory snapshot is missing.",
        )

    rules_data = snapshot.snapshot_data.get("rules", [])

    # 4. Execute orchestrator
    audit_run = await execute_audit(
        workspace_id=w_id,
        client_id=c_id,
        asset_id=a_id,
        asset_version_id=v_id,
        snapshot_id=snapshot.id,
        rules=rules_data,
        text_content=version.text_content,
        image_bytes=None,  # pure text audit for this version
        user_id=ctx.user_id,
        db=db,
    )

    # Reload relationships for response
    return await _build_audit_response(audit_run.id, db)


@router.get(
    "/workspaces/{w_id}/clients/{c_id}/audits/{run_id}",
    response_model=AuditRunResponse,
    summary="Retrieve diagnostic scorecard and audit results",
)
async def get_audit_run(
    w_id: uuid.UUID = Path(..., description="Workspace ID"),
    c_id: uuid.UUID = Path(..., description="Client Brand ID"),
    run_id: uuid.UUID = Path(..., description="Audit Run ID"),
    ctx: SecurityContext = Depends(require_client_member),
    db: AsyncSession = Depends(get_db),
) -> AuditRunResponse:
    run = await db.get(AuditRun, run_id)
    if not run or run.workspace_id != w_id or run.client_id != c_id:
        raise ProblemException(
            status=status.HTTP_404_NOT_FOUND,
            code="AUDIT_NOT_FOUND",
            title="Not Found",
            detail="Audit run not found.",
        )
    return await _build_audit_response(run_id, db)


@router.post(
    "/workspaces/{w_id}/clients/{c_id}/audits/{run_id}/remediate",
    response_model=AssetVersionResponse,
    summary="Accept surgical correction suggestions and fork remediated version (TASK-025)",
)
async def remediate_content(
    payload: RemediationRequest,
    w_id: uuid.UUID = Path(..., description="Workspace ID"),
    c_id: uuid.UUID = Path(..., description="Client Brand ID"),
    run_id: uuid.UUID = Path(..., description="Audit Run ID"),
    ctx: SecurityContext = Depends(require_client_member),
    db: AsyncSession = Depends(get_db),
) -> AssetVersionResponse:
    run = await db.get(AuditRun, run_id)
    if not run or run.workspace_id != w_id or run.client_id != c_id:
        raise ProblemException(
            status=status.HTTP_404_NOT_FOUND,
            code="AUDIT_NOT_FOUND",
            title="Not Found",
            detail="Audit run not found.",
        )

    version = await db.get(AssetVersion, run.asset_version_id)
    if not version or not version.text_content:
        raise ProblemException(
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="NOT_REMEDIABLE",
            title="Unprocessable Entity",
            detail="Version has no text content to remediate.",
        )

    # Fetch accepted suggestions
    sugg_stmt = select(CorrectionSuggestion).where(
        CorrectionSuggestion.id.in_(payload.suggestion_ids),
        CorrectionSuggestion.audit_run_id == run_id,
    )
    suggestions = (await db.execute(sugg_stmt)).scalars().all()
    if not suggestions:
        raise ProblemException(
            status=status.HTTP_404_NOT_FOUND,
            code="SUGGESTIONS_NOT_FOUND",
            title="Not Found",
            detail="None of the specified suggestions exist for this audit run.",
        )

    # Get finding locations for surgical spans
    corrections_payload = []
    for s in suggestions:
        finding = await db.get(AuditFinding, s.finding_id)
        corrections_payload.append(
            {
                "original_text": s.original_text,
                "suggested_text": s.suggested_text,
                "location_start": finding.location_start if finding else None,
                "location_end": finding.location_end if finding else None,
            }
        )
        # ADR-005: CorrectionSuggestion is historical audit run evidence and immutable.
        # The remediation application is recorded on the remediated AssetVersion
        # (created_from_correction_id=suggestions[0].id).

    remediated_text = apply_surgical_corrections(version.text_content, corrections_payload)

    new_version = await create_remediated_version(
        workspace_id=w_id,
        client_id=c_id,
        asset_id=run.asset_id,
        parent_version_id=version.id,
        remediated_text=remediated_text,
        primary_correction_id=suggestions[0].id,
        user_id=ctx.user_id,
        db=db,
    )

    return AssetVersionResponse(
        version_id=new_version.id,
        asset_id=new_version.asset_id,
        version_number=new_version.version_number,
        text_content=new_version.text_content,
        sha256_hash=new_version.sha256_hash,
        created_from_correction_id=new_version.created_from_correction_id,
        created_at=new_version.created_at,
    )


async def _build_audit_response(run_id: uuid.UUID, db: AsyncSession) -> AuditRunResponse:
    stmt = (
        select(AuditRun)
        .where(AuditRun.id == run_id)
        .options(
            selectinload(AuditRun.checks),
            selectinload(AuditRun.findings).selectinload(AuditFinding.suggestions),
        )
    )
    run = (await db.execute(stmt)).scalar_one()

    checks_out = [
        CheckResponse(
            check_id=c.id,
            engine_type=c.engine_type,
            status=c.status,
            execution_time_ms=c.execution_time_ms,
            summary_details=c.summary_details,
        )
        for c in run.checks
    ]

    findings_out = [
        FindingResponse(
            finding_id=f.id,
            rule_id=f.rule_id,
            rule_code=f.rule_code,
            severity=f.severity,
            message=f.message,
            location_start=f.location_start,
            location_end=f.location_end,
            snippet=f.snippet,
            evidence=f.evidence,
            suggestions=[
                SuggestionResponse(
                    suggestion_id=s.id,
                    finding_id=s.finding_id,
                    original_text=s.original_text,
                    suggested_text=s.suggested_text,
                    rationale=s.rationale,
                    applied_at=s.applied_at,
                )
                for s in f.suggestions
            ],
        )
        for f in run.findings
    ]

    return AuditRunResponse(
        audit_run_id=run.id,
        asset_id=run.asset_id,
        asset_version_id=run.asset_version_id,
        snapshot_id=run.snapshot_id,
        status=run.status,
        overall_verdict=run.overall_verdict,
        created_at=run.created_at,
        completed_at=run.completed_at,
        checks=checks_out,
        findings=findings_out,
    )
