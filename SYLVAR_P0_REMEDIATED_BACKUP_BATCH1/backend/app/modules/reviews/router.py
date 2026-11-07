"""Human Review, Brand Manager Approval & Compliance Certificate API routes (Domain G)."""
import hashlib
import json
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
from app.models.audit import AuditFinding, AuditRun, AuditRunStatus
from app.models.content import AssetVersion, ContentAsset
from app.models.memory import BrandMemorySnapshot
from app.models.review import ApprovalRequest, ApprovalStatus, ComplianceCertificate
from app.modules.auth.pipeline import SecurityContext, require_brand_manager, require_client_member

router = APIRouter(tags=["Human Review & Compliance"])


class ReviewSubmitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: uuid.UUID
    asset_version_id: uuid.UUID
    audit_run_id: uuid.UUID
    submission_notes: str | None = Field(default=None, max_length=1000)


class ReviewDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: ApprovalStatus = Field(..., description="APPROVED, REJECTED, or CHANGES_REQUESTED")
    decision_notes: str | None = Field(default=None, max_length=2000)
    advisory_acknowledgments: list[str] = Field(default_factory=list)


class CertificateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    certificate_id: uuid.UUID
    asset_version_id: uuid.UUID
    snapshot_hash: str
    certificate_hash: str
    certificate_payload: dict[str, Any]
    issued_at: datetime


class ReviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    review_id: uuid.UUID
    workspace_id: uuid.UUID
    client_id: uuid.UUID
    asset_id: uuid.UUID
    asset_version_id: uuid.UUID
    audit_run_id: uuid.UUID
    status: str
    decision_notes: str | None = None
    advisory_acknowledgments: list[str] = []
    submitted_by_user_id: uuid.UUID
    decided_by_user_id: uuid.UUID | None = None
    decided_at: datetime | None = None
    created_at: datetime
    certificate: CertificateResponse | None = None


@router.post(
    "/workspaces/{w_id}/clients/{c_id}/reviews",
    response_model=ReviewResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit audited asset version for Brand Manager approval (TASK-026)",
)
async def submit_for_review(
    payload: ReviewSubmitRequest,
    w_id: uuid.UUID = Path(..., description="Workspace ID"),
    c_id: uuid.UUID = Path(..., description="Client Brand ID"),
    ctx: SecurityContext = Depends(require_client_member),
    db: AsyncSession = Depends(get_db),
) -> ReviewResponse:
    # 1. Verify content asset belongs to client
    asset = await db.get(ContentAsset, payload.asset_id)
    if not asset or asset.workspace_id != w_id or asset.client_id != c_id:
        raise ProblemException(
            status=status.HTTP_404_NOT_FOUND,
            code="ASSET_NOT_FOUND",
            title="Not Found",
            detail="Content asset not found in this client brand.",
        )

    # 2. Verify asset version belongs to asset and client
    version = await db.get(AssetVersion, payload.asset_version_id)
    if (
        not version
        or version.asset_id != payload.asset_id
        or version.workspace_id != w_id
        or version.client_id != c_id
    ):
        raise ProblemException(
            status=status.HTTP_404_NOT_FOUND,
            code="VERSION_NOT_FOUND",
            title="Not Found",
            detail="Asset version not found for this asset.",
        )

    # 3. Verify audit run belongs to this client and exact version (Resolves C-07)
    audit = await db.get(AuditRun, payload.audit_run_id)
    if not audit or audit.workspace_id != w_id or audit.client_id != c_id:
        raise ProblemException(
            status=status.HTTP_404_NOT_FOUND,
            code="AUDIT_NOT_FOUND",
            title="Not Found",
            detail="Specified audit run not found.",
        )

    if audit.asset_id != payload.asset_id or audit.asset_version_id != payload.asset_version_id:
        raise ProblemException(
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="AUDIT_MISMATCH",
            title="Unprocessable Entity",
            detail="Audit run does not correspond to the submitted content version.",
        )

    if audit.status != AuditRunStatus.COMPLETED.value:
        raise ProblemException(
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="AUDIT_NOT_COMPLETED",
            title="Unprocessable Entity",
            detail=f"Audit run status is '{audit.status}'. Only COMPLETED audits can be submitted for review.",
        )

    # 4. Prevent submission if content is BLOCKED by critical violations
    if audit.overall_verdict == "BLOCKED":
        raise ProblemException(
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="AUDIT_BLOCKED",
            title="Unprocessable Entity",
            detail="Cannot submit blocked content for approval. Resolve all critical findings first.",
        )

    # 5. Prevent duplicate pending review requests for the same version
    pending_stmt = select(ApprovalRequest).where(
        ApprovalRequest.asset_version_id == payload.asset_version_id,
        ApprovalRequest.status == ApprovalStatus.PENDING.value,
    )
    existing_pending = (await db.execute(pending_stmt)).scalar_one_or_none()
    if existing_pending:
        raise ProblemException(
            status=status.HTTP_409_CONFLICT,
            code="REVIEW_ALREADY_PENDING",
            title="Conflict",
            detail="A review request is already pending for this asset version.",
        )

    # 6. Create ApprovalRequest
    req = ApprovalRequest(
        workspace_id=w_id,
        client_id=c_id,
        asset_id=payload.asset_id,
        asset_version_id=payload.asset_version_id,
        audit_run_id=payload.audit_run_id,
        submitted_by_user_id=ctx.user_id,
        status=ApprovalStatus.PENDING.value,
        decision_notes=payload.submission_notes,
    )
    db.add(req)
    await db.flush()

    return ReviewResponse(
        review_id=req.id,
        workspace_id=req.workspace_id,
        client_id=req.client_id,
        asset_id=req.asset_id,
        asset_version_id=req.asset_version_id,
        audit_run_id=req.audit_run_id,
        status=req.status,
        decision_notes=req.decision_notes,
        advisory_acknowledgments=req.advisory_acknowledgments,
        submitted_by_user_id=req.submitted_by_user_id,
        decided_by_user_id=req.decided_by_user_id,
        decided_at=req.decided_at,
        created_at=req.created_at,
        certificate=None,
    )


@router.get(
    "/workspaces/{w_id}/clients/{c_id}/reviews",
    response_model=list[ReviewResponse],
    summary="List review requests for client brand",
)
async def list_reviews(
    w_id: uuid.UUID = Path(..., description="Workspace ID"),
    c_id: uuid.UUID = Path(..., description="Client Brand ID"),
    ctx: SecurityContext = Depends(require_client_member),
    db: AsyncSession = Depends(get_db),
) -> list[ReviewResponse]:
    stmt = (
        select(ApprovalRequest)
        .where(
            ApprovalRequest.workspace_id == w_id,
            ApprovalRequest.client_id == c_id,
        )
        .options(selectinload(ApprovalRequest.certificate))
        .order_by(ApprovalRequest.created_at.desc())
    )
    requests = (await db.execute(stmt)).scalars().all()

    return [
        ReviewResponse(
            review_id=r.id,
            workspace_id=r.workspace_id,
            client_id=r.client_id,
            asset_id=r.asset_id,
            asset_version_id=r.asset_version_id,
            audit_run_id=r.audit_run_id,
            status=r.status,
            decision_notes=r.decision_notes,
            advisory_acknowledgments=r.advisory_acknowledgments,
            submitted_by_user_id=r.submitted_by_user_id,
            decided_by_user_id=r.decided_by_user_id,
            decided_at=r.decided_at,
            created_at=r.created_at,
            certificate=CertificateResponse(
                certificate_id=r.certificate.id,
                asset_version_id=r.certificate.asset_version_id,
                snapshot_hash=r.certificate.snapshot_hash,
                certificate_hash=r.certificate.certificate_hash,
                certificate_payload=r.certificate.certificate_payload,
                issued_at=r.certificate.issued_at,
            )
            if r.certificate
            else None,
        )
        for r in requests
    ]


@router.post(
    "/workspaces/{w_id}/clients/{c_id}/reviews/{req_id}/decision",
    response_model=ReviewResponse,
    summary="Brand Manager reviews and decides on content (TASK-026)",
)
async def decide_review(
    payload: ReviewDecisionRequest,
    w_id: uuid.UUID = Path(..., description="Workspace ID"),
    c_id: uuid.UUID = Path(..., description="Client Brand ID"),
    req_id: uuid.UUID = Path(..., description="Review Request ID"),
    ctx: SecurityContext = Depends(require_brand_manager),
    db: AsyncSession = Depends(get_db),
) -> ReviewResponse:
    req = await db.get(ApprovalRequest, req_id)
    if not req or req.workspace_id != w_id or req.client_id != c_id:
        raise ProblemException(
            status=status.HTTP_404_NOT_FOUND,
            code="REVIEW_NOT_FOUND",
            title="Not Found",
            detail="Review request not found.",
        )

    # 1. State transition check (Resolves C-08: Disallow repeated or contradictory decisions)
    if req.status != ApprovalStatus.PENDING.value:
        raise ProblemException(
            status=status.HTTP_409_CONFLICT,
            code="REVIEW_ALREADY_DECIDED",
            title="Conflict",
            detail=f"Review request has already been decided with terminal status '{req.status}'.",
        )

    # 2. Advisory warning acknowledgment validation (Resolves M-09)
    if payload.decision == ApprovalStatus.APPROVED:
        # Fetch non-critical findings for this audit run
        findings_stmt = select(AuditFinding).where(
            AuditFinding.audit_run_id == req.audit_run_id,
            AuditFinding.severity.in_(["MAJOR", "MINOR", "ADVISORY"]),
        )
        advisory_findings = (await db.execute(findings_stmt)).scalars().all()
        advisory_finding_ids = {str(f.id) for f in advisory_findings}

        submitted_acks = set(payload.advisory_acknowledgments)
        invalid_acks = submitted_acks - advisory_finding_ids
        if invalid_acks:
            raise ProblemException(
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                code="INVALID_ACKNOWLEDGMENT_IDS",
                title="Unprocessable Entity",
                detail=f"Submitted advisory acknowledgment IDs do not exist in this audit run: {list(invalid_acks)}",
            )

        unacknowledged = advisory_finding_ids - submitted_acks
        if unacknowledged:
            raise ProblemException(
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                code="UNACKNOWLEDGED_ADVISORY_FINDINGS",
                title="Unprocessable Entity",
                detail=f"All {len(advisory_finding_ids)} advisory findings must be acknowledged before approval. {len(unacknowledged)} unacknowledged.",
            )

    req.status = payload.decision.value
    req.decision_notes = payload.decision_notes
    req.advisory_acknowledgments = payload.advisory_acknowledgments
    req.decided_by_user_id = ctx.user_id
    req.decided_at = datetime.now(UTC)

    cert_response: CertificateResponse | None = None

    # If APPROVED: Issue immutable verifiable ComplianceCertificate
    if payload.decision == ApprovalStatus.APPROVED:
        version = await db.get(AssetVersion, req.asset_version_id)
        asset = await db.get(ContentAsset, req.asset_id)
        audit = await db.get(AuditRun, req.audit_run_id)
        snapshot = await db.get(BrandMemorySnapshot, audit.snapshot_id) if audit else None

        snap_hash = snapshot.snapshot_hash if snapshot else "UNKNOWN_SNAPSHOT"

        cert_payload = {
            "certificate_version": "1.0",
            "workspace_id": str(w_id),
            "client_id": str(c_id),
            "asset_id": str(req.asset_id),
            "asset_title": asset.title if asset else "Untitled",
            "asset_version_number": version.version_number if version else 1,
            "asset_sha256": version.sha256_hash if version else "",
            "snapshot_hash": snap_hash,
            "audit_verdict": audit.overall_verdict if audit else "PASS",
            "advisory_acknowledgments": payload.advisory_acknowledgments,
            "approved_by_user_id": str(ctx.user_id),
            "approved_at": req.decided_at.isoformat(),
        }

        canonical_json = json.dumps(cert_payload, sort_keys=True, separators=(",", ":"))
        cert_hash = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

        cert = ComplianceCertificate(
            workspace_id=w_id,
            client_id=c_id,
            asset_version_id=req.asset_version_id,
            approval_request_id=req.id,
            snapshot_hash=snap_hash,
            certificate_hash=cert_hash,
            certificate_payload=cert_payload,
            issued_at=req.decided_at,
        )
        db.add(cert)
        await db.flush()

        cert_response = CertificateResponse(
            certificate_id=cert.id,
            asset_version_id=cert.asset_version_id,
            snapshot_hash=cert.snapshot_hash,
            certificate_hash=cert.certificate_hash,
            certificate_payload=cert.certificate_payload,
            issued_at=cert.issued_at,
        )

    await db.flush()

    return ReviewResponse(
        review_id=req.id,
        workspace_id=req.workspace_id,
        client_id=req.client_id,
        asset_id=req.asset_id,
        asset_version_id=req.asset_version_id,
        audit_run_id=req.audit_run_id,
        status=req.status,
        decision_notes=req.decision_notes,
        advisory_acknowledgments=req.advisory_acknowledgments,
        submitted_by_user_id=req.submitted_by_user_id,
        decided_by_user_id=req.decided_by_user_id,
        decided_at=req.decided_at,
        created_at=req.created_at,
        certificate=cert_response,
    )


@router.get(
    "/workspaces/{w_id}/clients/{c_id}/reviews/{req_id}/certificate",
    response_model=CertificateResponse,
    summary="Export compliance certificate and manifest",
)
async def get_certificate(
    w_id: uuid.UUID = Path(..., description="Workspace ID"),
    c_id: uuid.UUID = Path(..., description="Client Brand ID"),
    req_id: uuid.UUID = Path(..., description="Review Request ID"),
    ctx: SecurityContext = Depends(require_client_member),
    db: AsyncSession = Depends(get_db),
) -> CertificateResponse:
    stmt = select(ComplianceCertificate).where(
        ComplianceCertificate.approval_request_id == req_id,
        ComplianceCertificate.workspace_id == w_id,
        ComplianceCertificate.client_id == c_id,
    )
    cert = (await db.execute(stmt)).scalar_one_or_none()
    if not cert:
        raise ProblemException(
            status=status.HTTP_404_NOT_FOUND,
            code="CERTIFICATE_NOT_FOUND",
            title="Not Found",
            detail="Compliance certificate not found for this review.",
        )

    return CertificateResponse(
        certificate_id=cert.id,
        asset_version_id=cert.asset_version_id,
        snapshot_hash=cert.snapshot_hash,
        certificate_hash=cert.certificate_hash,
        certificate_payload=cert.certificate_payload,
        issued_at=cert.issued_at,
    )
