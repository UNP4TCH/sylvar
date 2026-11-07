"""Surgical AI Remediation Engine (TASK-025).

Applies precise minimal surgical edits to content assets based on accepted correction suggestions.
Maintains version forking with `created_from_correction_id` and increments `version_number`.
"""
import hashlib
import unicodedata
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ProblemException
from app.models.content import AssetVersion, ContentAsset


def apply_surgical_corrections(
    original_text: str, corrections: list[dict[str, Any]]
) -> str:
    """Apply accepted surgical edits to original text.

    Operates strictly on Unicode NFC-normalized text.
    Validates all spans against original normalized text slices.
    Detects and rejects overlapping corrections or conflicting replacements with 422 SUGGESTION_CONFLICT.
    Single-pass reconstruction from original text slices.
    """
    if not corrections:
        return unicodedata.normalize("NFC", original_text or "")

    norm_text = unicodedata.normalize("NFC", original_text or "")

    resolved_edits: list[dict[str, Any]] = []

    for c in corrections:
        orig = unicodedata.normalize("NFC", c.get("original_text", "") or "")
        sugg = unicodedata.normalize("NFC", c.get("suggested_text", "") or "")
        start = c.get("location_start")
        end = c.get("location_end")

        # Validate span if provided
        valid_span = False
        if (
            start is not None
            and end is not None
            and isinstance(start, int)
            and isinstance(end, int)
            and 0 <= start <= end <= len(norm_text)
        ):
            if norm_text[start:end] == orig:
                valid_span = True

        if valid_span:
            resolved_edits.append({
                "start": start,
                "end": end,
                "original_text": orig,
                "suggested_text": sugg,
            })
        else:
            # If span is invalid/missing, use original_text ONLY when it occurs exactly once in norm_text
            if not orig:
                raise ProblemException(
                    status=422,
                    title="Suggestion Conflict",
                    code="SUGGESTION_CONFLICT",
                    detail="Correction target text is empty or missing.",
                )

            count = norm_text.count(orig)
            if count == 0:
                raise ProblemException(
                    status=422,
                    title="Suggestion Conflict",
                    code="SUGGESTION_CONFLICT",
                    detail=f"Target text '{orig}' not found in source text.",
                )
            elif count > 1:
                raise ProblemException(
                    status=422,
                    title="Suggestion Conflict",
                    code="SUGGESTION_CONFLICT",
                    detail=f"Target text '{orig}' occurs {count} times in source text; span location is ambiguous.",
                )
            else:
                idx = norm_text.index(orig)
                resolved_edits.append({
                    "start": idx,
                    "end": idx + len(orig),
                    "original_text": orig,
                    "suggested_text": sugg,
                })

    # Deduplicate identical (span, replacement) corrections
    unique_edits: list[dict[str, Any]] = []
    seen = set()
    for e in resolved_edits:
        key = (e["start"], e["end"], e["original_text"], e["suggested_text"])
        if key in seen:
            continue
        seen.add(key)
        unique_edits.append(e)

    # Sort edits by start offset ascending, then end offset ascending
    unique_edits.sort(key=lambda x: (x["start"], x["end"]))

    # Check for conflicting replacements targeting same span or overlapping spans
    for i in range(len(unique_edits)):
        curr = unique_edits[i]
        for j in range(i + 1, len(unique_edits)):
            other = unique_edits[j]
            # Conflicting replacement on identical span
            if curr["start"] == other["start"] and curr["end"] == other["end"]:
                raise ProblemException(
                    status=422,
                    title="Suggestion Conflict",
                    code="SUGGESTION_CONFLICT",
                    detail=f"Conflicting replacements for span [{curr['start']}:{curr['end']}].",
                )
            # Overlapping spans (since sorted by start, other["start"] >= curr["start"])
            if other["start"] < curr["end"]:
                raise ProblemException(
                    status=422,
                    title="Suggestion Conflict",
                    code="SUGGESTION_CONFLICT",
                    detail=f"Overlapping corrections detected between spans [{curr['start']}:{curr['end']}] and [{other['start']}:{other['end']}].",
                )

    # Single-pass reconstruction using slices from original normalized text
    result_pieces = []
    last_idx = 0
    for e in unique_edits:
        start = e["start"]
        end = e["end"]
        sugg = e["suggested_text"]
        result_pieces.append(norm_text[last_idx:start])
        result_pieces.append(sugg)
        last_idx = end
    result_pieces.append(norm_text[last_idx:])

    return "".join(result_pieces)


async def create_remediated_version(
    workspace_id: uuid.UUID,
    client_id: uuid.UUID,
    asset_id: uuid.UUID,
    parent_version_id: uuid.UUID,
    remediated_text: str,
    primary_correction_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> AssetVersion:
    """Create a new version for an asset after applying corrections.

    Locks the parent ContentAsset with SELECT ... FOR UPDATE scoped by workspace, client, and asset ID.
    Calculates next version number while holding the lock.
    Safely handles IntegrityError and maps to HTTP 409 VERSION_CONFLICT.
    """
    # 1. Lock the parent ContentAsset scoped by workspace, client, and asset ID
    lock_stmt = (
        select(ContentAsset)
        .where(
            ContentAsset.id == asset_id,
            ContentAsset.workspace_id == workspace_id,
            ContentAsset.client_id == client_id,
        )
        .with_for_update()
    )
    asset = (await db.execute(lock_stmt)).scalar_one_or_none()
    if not asset:
        raise ProblemException(
            status=404,
            title="Not Found",
            code="ASSET_NOT_FOUND",
            detail="Content asset not found for locking.",
        )

    # 2. Check if a version with identical content hash already exists for this asset (Finding D reuse requirement)
    sha256 = hashlib.sha256(remediated_text.encode("utf-8")).hexdigest()
    existing_stmt = select(AssetVersion).where(
        AssetVersion.asset_id == asset_id,
        AssetVersion.sha256_hash == sha256,
    )
    existing_version = (await db.execute(existing_stmt)).scalar_one_or_none()
    if existing_version:
        return existing_version

    # 3. Calculate next version number while holding the lock
    v_stmt = select(func.coalesce(func.max(AssetVersion.version_number), 0)).where(
        AssetVersion.asset_id == asset_id
    )
    max_v = (await db.execute(v_stmt)).scalar() or 0
    next_v = max_v + 1

    new_version = AssetVersion(
        workspace_id=workspace_id,
        client_id=client_id,
        asset_id=asset_id,
        version_number=next_v,
        text_content=remediated_text,
        sha256_hash=sha256,
        created_from_correction_id=primary_correction_id,
        created_by_user_id=user_id,
    )
    db.add(new_version)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise ProblemException(
            status=409,
            title="Version Conflict",
            code="VERSION_CONFLICT",
            detail=f"Concurrent version creation conflict for asset {asset_id}.",
        ) from exc

    return new_version
