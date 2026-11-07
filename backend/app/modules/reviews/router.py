"""Human Review, Brand Manager Approval & Compliance Certificate API routes (Domain G)."""
import enum
import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Path, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import ProblemException
from app.db.session import get_db
from app.models.audit import AuditCheck, AuditFinding, AuditRun, AuditRunStatus
from app.models.content import AssetVersion, ContentAsset
from app.models.memory import BrandMemorySnapshot
from app.models.review import ApprovalRequest, ApprovalStatus, ComplianceCertificate
from app.modules.auth.pipeline import SecurityContext, require_brand_manager, require_client_member

router = APIRouter(tags=["Human Review & Compliance"])


class ReviewDecision(str, enum.Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"


class ReviewSubmitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: uuid.UUID
    asset_version_id: uuid.UUID
    audit_run_id: uuid.UUID
    submission_notes: str | None = Field(default=None, max_length=1000)


class ReviewDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: ReviewDecision = Field(
        ..., description="Terminal review decision: APPROVED, REJECTED, or CHANGES_REQUESTED"
    )
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

    # 5. Prevent submission if content is already approved or has a pending review
    approved_stmt = select(ApprovalRequest).where(
        ApprovalRequest.asset_version_id == payload.asset_version_id,
        ApprovalRequest.status == ApprovalStatus.APPROVED.value,
    )
    existing_approved = (await db.execute(approved_stmt)).scalar_one_or_none()
    if existing_approved:
        raise ProblemException(
            status=status.HTTP_409_CONFLICT,
            code="VERSION_ALREADY_APPROVED",
            title="Conflict",
            detail="This asset version has already been approved and cannot be resubmitted.",
        )

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
    try:
        db.add(req)
        await db.flush()
        await db.commit()  # N3: commit visibility
    except IntegrityError:
        await db.rollback()
        raise ProblemException(
            status=status.HTTP_409_CONFLICT,
            code="REVIEW_ALREADY_PENDING",
            title="Conflict",
            detail="A review request is already pending for this asset version.",
        )

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
    stmt = (
        select(ApprovalRequest)
        .where(
            ApprovalRequest.id == req_id,
            ApprovalRequest.workspace_id == w_id,
            ApprovalRequest.client_id == c_id,
        )
        .with_for_update()
    )
    req = (await db.execute(stmt)).scalar_one_or_none()
    if not req:
        raise ProblemException(
            status=status.HTTP_404_NOT_FOUND,
            code="REVIEW_NOT_FOUND",
            title="Not Found",
            detail="Review request not found.",
        )

    # 1. Reject invalid decision (Finding A: PENDING cannot be submitted as a decision)
    if payload.decision == "PENDING" or payload.decision not in (
        ReviewDecision.APPROVED,
        ReviewDecision.REJECTED,
        ReviewDecision.CHANGES_REQUESTED,
    ):
        raise ProblemException(
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="INVALID_REVIEW_DECISION",
            title="Invalid Decision",
            detail="Review decision must be APPROVED, REJECTED, or CHANGES_REQUESTED. PENDING is not an allowed decision.",
        )

    # 2. State transition check (Resolves C-08: Disallow repeated or contradictory decisions)
    if req.status != ApprovalStatus.PENDING.value:
        raise ProblemException(
            status=status.HTTP_409_CONFLICT,
            code="REVIEW_ALREADY_DECIDED",
            title="Conflict",
            detail=f"Review request has already been decided with terminal status '{req.status}'.",
        )

    # 3. Load Asset & Version under locked transaction for complete Separation of Duties (Finding B)
    asset = await db.get(ContentAsset, req.asset_id)
    version = await db.get(AssetVersion, req.asset_version_id)

    if payload.decision == ReviewDecision.APPROVED:
        if not asset or not version or not asset.created_by_user_id or not version.created_by_user_id:
            raise ProblemException(
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                code="OWNERSHIP_EVIDENCE_MISSING",
                title="Unprocessable Entity",
                detail="Content asset or version ownership records are missing; cannot establish separation of duties.",
            )

        prohibited_creators = {
            req.submitted_by_user_id,
            asset.created_by_user_id,
            version.created_by_user_id,
        }

        if ctx.user_id in prohibited_creators:
            raise ProblemException(
                status=status.HTTP_403_FORBIDDEN,
                code="CREATOR_CANNOT_APPROVE_OWN_SUBMISSION",
                title="Separation of Duties Violation",
                detail="The reviewer authored or submitted this content and cannot approve it. An independent Brand Manager must review and approve.",
            )

    # 4. Require reviewer comments on rejection or change request
    if payload.decision in (ReviewDecision.REJECTED, ReviewDecision.CHANGES_REQUESTED):
        if not payload.decision_notes or not payload.decision_notes.strip():
            raise ProblemException(
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                code="REVIEWER_COMMENTS_REQUIRED",
                title="Reviewer Comments Required",
                detail="Reviewer comments are mandatory when rejecting or requesting changes.",
            )

    # 5. Advisory warning acknowledgment validation (Resolves M-09)
    if payload.decision == ReviewDecision.APPROVED:
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

    cert_response: CertificateResponse | None = None

    # If APPROVED: Verify evidence and issue immutable verifiable ComplianceCertificate (Finding G & v1.1)
    if payload.decision == ReviewDecision.APPROVED:
        # Ensure a certificate does not already exist for this approval request or asset version (Finding F)
        existing_cert_stmt = select(ComplianceCertificate).where(
            (ComplianceCertificate.approval_request_id == req.id)
            | (ComplianceCertificate.asset_version_id == req.asset_version_id)
        )
        if (await db.execute(existing_cert_stmt)).scalar_one_or_none():
            raise ProblemException(
                status=status.HTTP_409_CONFLICT,
                code="CERTIFICATE_ALREADY_ISSUED",
                title="Conflict",
                detail="A compliance certificate has already been issued for this asset version.",
            )

        # Check if version was already approved in another request (Finding F)
        existing_approved_stmt = select(ApprovalRequest).where(
            ApprovalRequest.asset_version_id == req.asset_version_id,
            ApprovalRequest.status == ApprovalStatus.APPROVED.value,
            ApprovalRequest.id != req.id,
        )
        if (await db.execute(existing_approved_stmt)).scalar_one_or_none():
            raise ProblemException(
                status=status.HTTP_409_CONFLICT,
                code="VERSION_ALREADY_APPROVED",
                title="Conflict",
                detail="This asset version has already been approved in another request.",
            )

        # Validate AuditRun evidence (Finding G)
        audit = await db.get(AuditRun, req.audit_run_id)
        if not audit:
            raise ProblemException(
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                code="CERTIFICATE_EVIDENCE_INCOMPLETE",
                title="Unprocessable Entity",
                detail="Audit run evidence is missing.",
            )

        if audit.status != AuditRunStatus.COMPLETED.value:
            raise ProblemException(
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                code="CERTIFICATE_EVIDENCE_INCOMPLETE",
                title="Unprocessable Entity",
                detail=f"Audit execution status must be COMPLETED, got '{audit.status}'.",
            )

        if audit.overall_verdict not in ("PASS", "WARNINGS"):
            raise ProblemException(
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                code="CERTIFICATE_EVIDENCE_INCOMPLETE",
                title="Unprocessable Entity",
                detail=f"Audit verdict must be PASS or WARNINGS to issue certificate, got '{audit.overall_verdict}'.",
            )

        if audit.asset_version_id != req.asset_version_id or audit.asset_id != req.asset_id:
            raise ProblemException(
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                code="CERTIFICATE_EVIDENCE_INCOMPLETE",
                title="Unprocessable Entity",
                detail="Audit run evidence does not match the submitted asset version.",
            )

        # Validate Memory Snapshot (Finding G & N8)
        snap_stmt = select(BrandMemorySnapshot).where(
            BrandMemorySnapshot.id == audit.snapshot_id,
            BrandMemorySnapshot.workspace_id == w_id,
            BrandMemorySnapshot.client_id == c_id,
        )
        snapshot = (await db.execute(snap_stmt)).scalar_one_or_none()
        if not snapshot or not snapshot.snapshot_hash or len(snapshot.snapshot_hash) != 64:
            raise ProblemException(
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                code="CERTIFICATE_EVIDENCE_INCOMPLETE",
                title="Unprocessable Entity",
                detail="Valid brand memory snapshot with 64-character SHA-256 hash is required for certification.",
            )
        snap_hash = snapshot.snapshot_hash

        # Validate Check Evidence (Finding G)
        checks_stmt = (
            select(AuditCheck)
            .where(AuditCheck.audit_run_id == audit.id)
            .order_by(AuditCheck.engine_type)
        )
        checks = (await db.execute(checks_stmt)).scalars().all()
        check_types = {chk.engine_type for chk in checks}
        if "TERMINOLOGY" not in check_types:
            raise ProblemException(
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                code="CERTIFICATE_EVIDENCE_INCOMPLETE",
                title="Unprocessable Entity",
                detail="Required TERMINOLOGY check evidence is missing from audit run.",
            )
        if "FACTUAL" not in check_types:
            raise ProblemException(
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                code="CERTIFICATE_EVIDENCE_INCOMPLETE",
                title="Unprocessable Entity",
                detail="Required FACTUAL check evidence is missing from audit run.",
            )

        # Check if audit run was executed under offline demo mode (A4)
        is_demo_certificate = False
        disclosures: list[str] = []
        factual_check = next((c for c in checks if c.engine_type == "FACTUAL"), None)
        if factual_check:
            details = factual_check.summary_details or {}
            if details.get("demo_mode") or details.get("engine_mode") != "gemini_live" or details.get("provider_error"):
                is_demo_certificate = True
                disclosures.append(
                    "DEMO ONLY: Factual verification was NOT performed by a live AI provider. "
                    "This certificate does NOT certify factual accuracy and cannot be used for production publication."
                )

        # Canonical audit evidence digest (Section 2)
        findings_stmt = (
            select(AuditFinding)
            .where(AuditFinding.audit_run_id == audit.id)
            .order_by(AuditFinding.rule_code, AuditFinding.id)
        )
        findings = (await db.execute(findings_stmt)).scalars().all()

        canonical_evidence_data = {
            "audit_run_id": str(audit.id),
            "asset_version_id": str(req.asset_version_id),
            "checks": [
                {
                    "engine_type": c.engine_type,
                    "status": c.status,
                    "execution_time_ms": c.execution_time_ms,
                    "summary_details": c.summary_details,
                }
                for c in checks
            ],
            "findings": [
                {
                    "rule_code": f.rule_code,
                    "severity": f.severity,
                    "message": f.message,
                    "location_start": f.location_start,
                    "location_end": f.location_end,
                }
                for f in findings
            ],
        }
        canonical_evidence_json = json.dumps(canonical_evidence_data, sort_keys=True, separators=(",", ":"))
        audit_evidence_sha256 = hashlib.sha256(canonical_evidence_json.encode("utf-8")).hexdigest()

        # Certificate Payload Version 1.1 (Section 2)
        cert_payload = {
            "certificate_version": "1.1",
            "certificate_type": "DEMO_COMPLIANCE_CERTIFICATE" if is_demo_certificate else "STANDARD_COMPLIANCE_CERTIFICATE",
            "is_demo_only": is_demo_certificate,
            "disclosures": disclosures,
            "workspace_id": str(w_id),
            "client_id": str(c_id),
            "asset_id": str(req.asset_id),
            "asset_title": asset.title if asset else "Untitled",
            "asset_version_id": str(req.asset_version_id),
            "asset_version_number": version.version_number if version else 1,
            "asset_sha256": version.sha256_hash if version else "",
            "audit_run_id": str(audit.id),
            "approval_request_id": str(req.id),
            "submitted_by_user_id": str(req.submitted_by_user_id),
            "audit_evidence_sha256": audit_evidence_sha256,
            "snapshot_hash": snap_hash,
            "audit_verdict": audit.overall_verdict,
            "advisory_acknowledgments": payload.advisory_acknowledgments,
            "approved_by_user_id": str(ctx.user_id),
            "approved_at": datetime.now(UTC).isoformat(),
        }

        canonical_cert_json = json.dumps(cert_payload, sort_keys=True, separators=(",", ":"))
        cert_hash = hashlib.sha256(canonical_cert_json.encode("utf-8")).hexdigest()

        # Update decision state on ApprovalRequest
        req.status = payload.decision.value
        req.decision_notes = payload.decision_notes
        req.advisory_acknowledgments = payload.advisory_acknowledgments
        req.decided_by_user_id = ctx.user_id
        req.decided_at = datetime.now(UTC)

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
        try:
            db.add(cert)
            await db.flush()
        except IntegrityError:
            await db.rollback()
            raise ProblemException(
                status=status.HTTP_409_CONFLICT,
                code="CERTIFICATE_ALREADY_ISSUED",
                title="Conflict",
                detail="A compliance certificate has already been issued for this asset version.",
            )

        cert_response = CertificateResponse(
            certificate_id=cert.id,
            asset_version_id=cert.asset_version_id,
            snapshot_hash=cert.snapshot_hash,
            certificate_hash=cert.certificate_hash,
            certificate_payload=cert.certificate_payload,
            issued_at=cert.issued_at,
        )
    else:
        # REJECTED or CHANGES_REQUESTED
        req.status = payload.decision.value
        req.decision_notes = payload.decision_notes
        req.advisory_acknowledgments = payload.advisory_acknowledgments
        req.decided_by_user_id = ctx.user_id
        req.decided_at = datetime.now(UTC)
        await db.flush()

    await db.commit()  # N3: explicit commit visibility

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
