"""Stage 3.3: Longitudinal Insights & Analytics Test Suite.

Verifies:
1. Tenant-scoped recurring-violation calculation and ordering.
2. Pass rate, block rate, and warnings rate percentage calculations.
3. Suggestion adoption rate metrics.
4. Temporal trend daily aggregation.
5. Strict separation between observed counts and inferred recommendations (PHASE.md).
"""
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.models.audit import AuditFinding, AuditRun, AuditVerdict, CorrectionSuggestion
from app.modules.analytics.calculator import compute_longitudinal_insights


def test_compute_longitudinal_insights_empty():
    ws_id = uuid.uuid4()
    cl_id = uuid.uuid4()

    res = compute_longitudinal_insights(
        workspace_id=ws_id,
        client_id=cl_id,
        period_days=30,
        audit_runs=[],
        findings=[],
        suggestions=[],
    )

    assert res.total_audits == 0
    assert res.pass_rate_pct == 0.0
    assert res.block_rate_pct == 0.0
    assert res.warnings_rate_pct == 0.0
    assert len(res.top_recurring_violations) == 0
    assert len(res.temporal_trends) == 0
    assert len(res.observed_insights) > 0
    assert len(res.inferred_recommendations) > 0


def test_compute_longitudinal_insights_with_historical_audits():
    ws_id = uuid.uuid4()
    cl_id = uuid.uuid4()
    asset1 = uuid.uuid4()
    asset2 = uuid.uuid4()

    now = datetime.now(UTC)
    yesterday = now - timedelta(days=1)

    # 4 audit runs: 2 PASS, 1 BLOCKED, 1 WARNINGS
    r1 = AuditRun(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        client_id=cl_id,
        asset_id=asset1,
        asset_version_id=uuid.uuid4(),
        snapshot_id=uuid.uuid4(),
        overall_verdict=AuditVerdict.PASS.value,
        created_at=now,
    )
    r2 = AuditRun(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        client_id=cl_id,
        asset_id=asset1,
        asset_version_id=uuid.uuid4(),
        snapshot_id=uuid.uuid4(),
        overall_verdict=AuditVerdict.BLOCKED.value,
        created_at=yesterday,
    )
    r3 = AuditRun(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        client_id=cl_id,
        asset_id=asset2,
        asset_version_id=uuid.uuid4(),
        snapshot_id=uuid.uuid4(),
        overall_verdict=AuditVerdict.WARNINGS.value,
        created_at=now,
    )
    r4 = AuditRun(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        client_id=cl_id,
        asset_id=asset2,
        asset_version_id=uuid.uuid4(),
        snapshot_id=uuid.uuid4(),
        overall_verdict=AuditVerdict.PASS.value,
        created_at=yesterday,
    )

    runs = [r1, r2, r3, r4]

    # Findings: 3 for TERM-001 across asset1 and asset2; 1 for FACT-002
    f1 = AuditFinding(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        client_id=cl_id,
        audit_run_id=r2.id,
        rule_code="TERM-001",
        severity="MAJOR",
        message="Forbidden term detected",
        snippet="old stack",
    )
    f2 = AuditFinding(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        client_id=cl_id,
        audit_run_id=r2.id,
        rule_code="TERM-001",
        severity="MAJOR",
        message="Forbidden term detected",
        snippet="legacy tool",
    )
    f3 = AuditFinding(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        client_id=cl_id,
        audit_run_id=r3.id,
        rule_code="TERM-001",
        severity="MAJOR",
        message="Forbidden term detected",
        snippet="legacy tool",
    )
    f4 = AuditFinding(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        client_id=cl_id,
        audit_run_id=r3.id,
        rule_code="FACT-002",
        severity="WARNING",
        message="Unverified claim",
        snippet="Fastest in industry",
    )

    findings = [f1, f2, f3, f4]

    # 4 suggestions: 3 applied, 1 unapplied -> 75% adoption rate
    s1 = CorrectionSuggestion(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        client_id=cl_id,
        audit_run_id=r2.id,
        finding_id=f1.id,
        original_text="old stack",
        suggested_text="modern stack",
        rationale="Upgrade",
        applied_at=now,
    )
    s2 = CorrectionSuggestion(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        client_id=cl_id,
        audit_run_id=r2.id,
        finding_id=f2.id,
        original_text="legacy tool",
        suggested_text="modern platform",
        rationale="Terminology",
        applied_at=now,
    )
    s3 = CorrectionSuggestion(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        client_id=cl_id,
        audit_run_id=r3.id,
        finding_id=f3.id,
        original_text="legacy tool",
        suggested_text="modern platform",
        rationale="Terminology",
        applied_at=now,
    )
    s4 = CorrectionSuggestion(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        client_id=cl_id,
        audit_run_id=r3.id,
        finding_id=f4.id,
        original_text="Fastest in industry",
        suggested_text="Industry-leading performance",
        rationale="Claim",
        applied_at=None,
    )

    suggestions = [s1, s2, s3, s4]

    res = compute_longitudinal_insights(
        workspace_id=ws_id,
        client_id=cl_id,
        period_days=30,
        audit_runs=runs,
        findings=findings,
        suggestions=suggestions,
    )

    assert res.total_audits == 4
    assert res.pass_rate_pct == 50.0
    assert res.block_rate_pct == 25.0
    assert res.warnings_rate_pct == 25.0

    # Recurring violations
    assert len(res.top_recurring_violations) == 2
    top = res.top_recurring_violations[0]
    assert top.rule_code == "TERM-001"
    assert top.violation_count == 3
    assert top.affected_assets_count == 2
    assert top.category == "TERMINOLOGY"

    # Remediation stats
    assert res.remediation_adoption.total_suggestions_generated == 4
    assert res.remediation_adoption.applied_suggestions_count == 3
    assert res.remediation_adoption.adoption_rate_pct == 75.0

    # Temporal Trends
    assert len(res.temporal_trends) == 2

    # Observed Insights vs Inferred Recommendations
    assert any("Conducted 4 compliance audits" in o for o in res.observed_insights)
    assert any("Top recurring violation is 'TERM-001'" in o for o in res.observed_insights)
    assert any("75.0% creator adoption rate" in o for o in res.observed_insights)
    assert any("TERM-001" in inf for inf in res.inferred_recommendations)

