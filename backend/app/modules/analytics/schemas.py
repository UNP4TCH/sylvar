"""Schemas for Longitudinal Insights & Recurring-Violation Analytics (Stage 3 Differentiator)."""
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RuleViolationStat(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_code: str
    category: str
    violation_count: int
    affected_assets_count: int
    severity: str
    sample_snippet: str | None = None


class TemporalTrendPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: str  # YYYY-MM-DD
    total_audits: int
    passed_count: int
    blocked_count: int
    warnings_count: int


class RemediationAdoptionStat(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_suggestions_generated: int
    applied_suggestions_count: int
    adoption_rate_pct: float


class LongitudinalInsightsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: uuid.UUID
    client_id: uuid.UUID
    period_days: int
    total_audits: int
    pass_rate_pct: float
    block_rate_pct: float
    warnings_rate_pct: float
    remediation_adoption: RemediationAdoptionStat
    top_recurring_violations: list[RuleViolationStat]
    temporal_trends: list[TemporalTrendPoint]
    observed_insights: list[str] = Field(
        ..., description="Factual metrics observed directly from audit history."
    )
    inferred_recommendations: list[str] = Field(
        ..., description="Data-driven suggestions to improve brand compliance."
    )

