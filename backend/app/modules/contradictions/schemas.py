"""Schemas for Guideline Contradiction Scanner & Human Resolution (Domain D)."""
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RuleExcerpt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_id: str
    rule_code: str
    category: str
    statement: str
    forbidden_term: str | None = None
    preferred_term: str | None = None
    hex_code: str | None = None
    source_document: str | None = None
    section: str | None = None


class ContradictionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conflict_id: str
    conflict_type: str  # TERMINOLOGY, COLOR, FACTUAL, AMBIGUITY
    severity: str  # CRITICAL, WARNING
    explanation: str
    rule_a: RuleExcerpt
    rule_b: RuleExcerpt
    suggested_resolutions: list[str] = [
        "KEEP_A",
        "KEEP_B",
        "MANUAL_OVERRIDE",
    ]


class ContradictionScanResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: uuid.UUID
    client_id: uuid.UUID
    rules_scanned_count: int
    contradictions_count: int
    has_critical_conflicts: bool
    contradictions: list[ContradictionItem]


class ResolutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resolution_action: str = Field(..., pattern="^(KEEP_A|KEEP_B|MANUAL_OVERRIDE)$")
    custom_statement: str | None = Field(default=None, max_length=1000)
    resolution_notes: str = Field(..., min_length=5, max_length=1000)


class ResolutionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conflict_id: str
    status: str  # RESOLVED
    resolution_action: str
    resolution_notes: str
    retained_rule_id: str | None = None
    deprecated_rule_id: str | None = None
    message: str

