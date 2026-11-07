"""Guideline documents and candidate rule staging API routes (Groups 6, 7 & 8)."""
import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Path, UploadFile, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import ProblemException
from app.db.session import get_db
from app.models.document import (
    CandidateStatus,
    DocumentSection,
    DocumentStatus,
    ExtractedCandidate,
    GuidelineDocument,
)
from app.modules.auth.pipeline import SecurityContext, require_brand_manager, require_client_member
from app.modules.documents.extractor import async_extract_candidate_rules
from app.modules.documents.parser import parse_document
from app.modules.documents.security import (
    detect_file_format,
    validate_docx_archive_safety,
    validate_file_size,
)

router = APIRouter(tags=["Guideline Documents"])


class DocumentUploadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    document_id: uuid.UUID
    title: str
    filename: str
    file_format: str
    file_size_bytes: int
    sha256: str
    processing_status: str
    candidate_count: int


class DocumentStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    document_id: uuid.UUID
    status: str
    candidate_count: int
    error_details: str | None = None


class CandidateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    candidate_id: uuid.UUID
    document_id: uuid.UUID
    category: str
    payload: dict[str, Any]
    review_status: str
    created_at: datetime


class CandidateUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payload: dict[str, Any] | None = None
    review_status: CandidateStatus = CandidateStatus.MODIFIED_APPROVED


@router.post(
    "/workspaces/{w_id}/clients/{c_id}/documents",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload brand guideline document (TASK-015)",
)
async def upload_document(
    w_id: uuid.UUID = Path(..., description="Workspace ID"),
    c_id: uuid.UUID = Path(..., description="Client Brand ID"),
    title: str = Form(..., min_length=2, max_length=255),
    file: UploadFile = File(...),
    ctx: SecurityContext = Depends(require_brand_manager),
    db: AsyncSession = Depends(get_db),
) -> DocumentUploadResponse:
    content = await file.read()
    filename = file.filename or "document.txt"

    # 1. Size & Format validation
    validate_file_size(len(content))
    file_format = detect_file_format(filename, content)

    # 2. DOCX Archive safety check
    if file_format == "DOCX":
        validate_docx_archive_safety(content)

    sha256 = hashlib.sha256(content).hexdigest()

    # 3. Create document record
    doc = GuidelineDocument(
        workspace_id=w_id,
        client_id=c_id,
        title=title,
        filename=filename,
        file_format=file_format,
        file_size_bytes=len(content),
        sha256_hash=sha256,
        processing_status=DocumentStatus.PARSING.value,
    )
    db.add(doc)
    await db.flush()

    # 4. Parse sections
    sections = parse_document(file_format, content)
    for sec in sections:
        db.add(
            DocumentSection(
                workspace_id=w_id,
                client_id=c_id,
                document_id=doc.id,
                section_number=sec.section_number,
                heading=sec.heading,
                content=sec.content,
                page_number=sec.page_number,
            )
        )

    # 5. Extract rule candidates (asynchronously in background thread, M-06)
    settings = get_settings()
    raw_candidates = await async_extract_candidate_rules(
        sections, api_key=settings.gemini_api_key, model=settings.gemini_model
    )
    created_candidates = []
    for cand in raw_candidates:
        ec = ExtractedCandidate(
            workspace_id=w_id,
            client_id=c_id,
            document_id=doc.id,
            category=cand["category"],
            payload=cand["payload"],
            review_status=CandidateStatus.PENDING_REVIEW.value,
        )
        db.add(ec)
        created_candidates.append(ec)

    doc.processing_status = DocumentStatus.EXTRACTED.value
    await db.flush()

    return DocumentUploadResponse(
        document_id=doc.id,
        title=doc.title,
        filename=doc.filename,
        file_format=doc.file_format,
        file_size_bytes=doc.file_size_bytes,
        sha256=doc.sha256_hash,
        processing_status=doc.processing_status,
        candidate_count=len(created_candidates),
    )


@router.get(
    "/workspaces/{w_id}/clients/{c_id}/documents/{d_id}/status",
    response_model=DocumentStatusResponse,
    summary="Poll document processing status",
)
async def get_document_status(
    w_id: uuid.UUID = Path(..., description="Workspace ID"),
    c_id: uuid.UUID = Path(..., description="Client Brand ID"),
    d_id: uuid.UUID = Path(..., description="Document ID"),
    ctx: SecurityContext = Depends(require_client_member),
    db: AsyncSession = Depends(get_db),
) -> DocumentStatusResponse:
    doc = await db.get(GuidelineDocument, d_id)
    if not doc or doc.workspace_id != w_id or doc.client_id != c_id:
        raise ProblemException(
            status=status.HTTP_404_NOT_FOUND,
            code="RESOURCE_NOT_FOUND",
            title="Not Found",
            detail="Document not found.",
        )

    cand_count_stmt = select(ExtractedCandidate).where(ExtractedCandidate.document_id == d_id)
    candidates = (await db.execute(cand_count_stmt)).scalars().all()

    return DocumentStatusResponse(
        document_id=doc.id,
        status=doc.processing_status,
        candidate_count=len(candidates),
        error_details=doc.error_details,
    )


@router.get(
    "/workspaces/{w_id}/clients/{c_id}/candidates",
    response_model=list[CandidateResponse],
    summary="List candidate rules awaiting review (Group 8)",
)
async def list_candidates(
    w_id: uuid.UUID = Path(..., description="Workspace ID"),
    c_id: uuid.UUID = Path(..., description="Client Brand ID"),
    review_status: str | None = None,
    ctx: SecurityContext = Depends(require_client_member),
    db: AsyncSession = Depends(get_db),
) -> list[CandidateResponse]:
    stmt = select(ExtractedCandidate).where(
        ExtractedCandidate.workspace_id == w_id,
        ExtractedCandidate.client_id == c_id,
    )
    if review_status:
        stmt = stmt.where(ExtractedCandidate.review_status == review_status)
    stmt = stmt.order_by(ExtractedCandidate.created_at.desc())
    candidates = (await db.execute(stmt)).scalars().all()

    return [
        CandidateResponse(
            candidate_id=cand.id,
            document_id=cand.document_id,
            category=cand.category,
            payload=cand.payload,
            review_status=cand.review_status,
            created_at=cand.created_at,
        )
        for cand in candidates
    ]


@router.patch(
    "/workspaces/{w_id}/clients/{c_id}/candidates/{cand_id}",
    response_model=CandidateResponse,
    summary="Modify or review candidate rule",
)
async def update_candidate(
    payload: CandidateUpdate,
    w_id: uuid.UUID = Path(..., description="Workspace ID"),
    c_id: uuid.UUID = Path(..., description="Client Brand ID"),
    cand_id: uuid.UUID = Path(..., description="Candidate ID"),
    ctx: SecurityContext = Depends(require_brand_manager),
    db: AsyncSession = Depends(get_db),
) -> CandidateResponse:
    cand = await db.get(ExtractedCandidate, cand_id)
    if not cand or cand.workspace_id != w_id or cand.client_id != c_id:
        raise ProblemException(
            status=status.HTTP_404_NOT_FOUND,
            code="RESOURCE_NOT_FOUND",
            title="Not Found",
            detail="Candidate rule not found.",
        )

    if payload.payload is not None:
        cand.payload = payload.payload
    cand.review_status = payload.review_status.value
    cand.updated_at = datetime.now(UTC)
    await db.flush()

    return CandidateResponse(
        candidate_id=cand.id,
        document_id=cand.document_id,
        category=cand.category,
        payload=cand.payload,
        review_status=cand.review_status,
        created_at=cand.created_at,
    )
