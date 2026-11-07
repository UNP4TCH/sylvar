"""Surgical AI Remediation Engine (TASK-025).

Applies precise minimal surgical edits to content assets based on accepted correction suggestions.
Maintains version forking with `created_from_correction_id` and increments `version_number`.
"""
import hashlib
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import AssetVersion


def apply_surgical_corrections(
    original_text: str, corrections: list[dict[str, Any]]
) -> str:
    """Apply accepted surgical edits to original text.

    Sorts edits from end of text to beginning to prevent offset drift.
    """
    # Filter corrections with valid spans
    valid_span_corrections = []
    fallback_corrections = []

    for c in corrections:
        start = c.get("location_start")
        end = c.get("location_end")
        orig = c.get("original_text", "")
        sugg = c.get("suggested_text", "")

        if (
            start is not None
            and end is not None
            and 0 <= start < end <= len(original_text)
            and original_text[start:end] == orig
        ):
            valid_span_corrections.append((start, end, orig, sugg))
            continue
        fallback_corrections.append((orig, sugg))

    # Apply span corrections in reverse order of start offset
    valid_span_corrections.sort(key=lambda x: x[0], reverse=True)
    remediated = original_text

    for start, end, _, sugg in valid_span_corrections:
        remediated = remediated[:start] + sugg + remediated[end:]

    # Apply any fallback direct replacements (replace only single target occurrence, M-12)
    for orig, sugg in fallback_corrections:
        if orig and orig in remediated:
            remediated = remediated.replace(orig, sugg, 1)

    return remediated


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
    """Create a new version for an asset after applying corrections."""
    # Find next version number
    v_stmt = select(func.coalesce(func.max(AssetVersion.version_number), 0)).where(
        AssetVersion.asset_id == asset_id
    )
    max_v = (await db.execute(v_stmt)).scalar() or 0
    next_v = max_v + 1

    sha256 = hashlib.sha256(remediated_text.encode("utf-8")).hexdigest()

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
    await db.flush()

    return new_version
