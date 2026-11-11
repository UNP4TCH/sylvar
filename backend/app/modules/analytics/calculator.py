"""Longitudinal Insights Calculation Engine (Stage 3 Differentiator).

Adheres to:
- Tenant-scoped aggregation across historical audit runs and findings.
- Explicitly separates observed counts from inferred recommendations (PHASE.md).
- Privacy-conscious summarization without leaking other clients or raw PII.
"""
from collections import defaultdict
from typing import Any

from app.models.audit import AuditFinding, AuditRun, CorrectionSuggestion
from app.modules.analytics.schemas import (
    LongitudinalInsightsResponse,
    RemediationAdoptionStat,
    RuleViolationStat,
    TemporalTrendPoint,
)


def compute_longitudinal_insights(
    workspace_id: Any,
    client_id: Any,
    period_days: int,
    audit_runs: list[AuditRun],
    findings: list[AuditFinding],
    suggestions: list[CorrectionSuggestion],
) -> LongitudinalInsightsResponse:
    total_audits = len(audit_runs)
    passed_count = sum(1 for r in audit_runs if r.overall_verdict == "PASS")
    blocked_count = sum(1 for r in audit_runs if r.overall_verdict == "BLOCKED")
    warnings_count = sum(1 for r in audit_runs if r.overall_verdict == "WARNINGS")

    pass_rate_pct = round((passed_count / total_audits) * 100, 1) if total_audits > 0 else 0.0
    block_rate_pct = round((blocked_count / total_audits) * 100, 1) if total_audits > 0 else 0.0
    warnings_rate_pct = round((warnings_count / total_audits) * 100, 1) if total_audits > 0 else 0.0

    # 1. Map audit runs to asset IDs for cross-asset impact
    run_to_asset = {r.id: r.asset_id for r in audit_runs}

    # 2. Group findings by rule code
    rule_groups: dict[str, list[AuditFinding]] = defaultdict(list)
    for f in findings:
        code = f.rule_code or "UNKNOWN"
        rule_groups[code].append(f)

    top_recurring: list[RuleViolationStat] = []
    for code, group in sorted(rule_groups.items(), key=lambda item: len(item[1]), reverse=True):
        affected_assets = {run_to_asset.get(f.audit_run_id) for f in group if f.audit_run_id in run_to_asset}
        sample_snippet = next((f.snippet for f in group if f.snippet), None)
        category = "TERMINOLOGY" if "TERM" in code else ("FACTUAL" if "FACT" in code else ("VISUAL" if "VISUAL" in code or "COLOR" in code else "POLICY"))
        top_recurring.append(
            RuleViolationStat(
                rule_code=code,
                category=category,
                violation_count=len(group),
                affected_assets_count=len(affected_assets),
                severity=group[0].severity,
                sample_snippet=sample_snippet,
            )
        )

    # 3. Remediation adoption
    total_sugg = len(suggestions)
    applied_sugg = sum(1 for s in suggestions if s.applied_at is not None)
    adoption_rate_pct = round((applied_sugg / total_sugg) * 100, 1) if total_sugg > 0 else 0.0

    remediation_stat = RemediationAdoptionStat(
        total_suggestions_generated=total_sugg,
        applied_suggestions_count=applied_sugg,
        adoption_rate_pct=adoption_rate_pct,
    )

    # 4. Temporal Trends (Grouped by date)
    date_buckets: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "pass": 0, "blocked": 0, "warnings": 0})
    for r in audit_runs:
        d_str = r.created_at.strftime("%Y-%m-%d") if r.created_at else "Unknown"
        date_buckets[d_str]["total"] += 1
        if r.overall_verdict == "PASS":
            date_buckets[d_str]["pass"] += 1
        elif r.overall_verdict == "BLOCKED":
            date_buckets[d_str]["blocked"] += 1
        elif r.overall_verdict == "WARNINGS":
            date_buckets[d_str]["warnings"] += 1

    temporal_trends: list[TemporalTrendPoint] = [
        TemporalTrendPoint(
            date=d,
            total_audits=counts["total"],
            passed_count=counts["pass"],
            blocked_count=counts["blocked"],
            warnings_count=counts["warnings"],
        )
        for d, counts in sorted(date_buckets.items())
    ]

    # 5. Distinct Observed Insights vs Inferred Recommendations (PHASE.md)
    observed: list[str] = [
        f"Conducted {total_audits} compliance audits ({passed_count} PASS, {blocked_count} BLOCKED, {warnings_count} WARNINGS).",
        f"Overall pre-publication pass rate is {pass_rate_pct}%.",
    ]
    if top_recurring:
        top = top_recurring[0]
        observed.append(
            f"Top recurring violation is '{top.rule_code}' with {top.violation_count} instances across {top.affected_assets_count} collateral assets."
        )
    if total_sugg > 0:
        observed.append(
            f"Surgical remediation engine generated {total_sugg} suggestions with a {adoption_rate_pct}% creator adoption rate."
        )

    inferred: list[str] = []
    if block_rate_pct > 30.0:
        inferred.append(
            "High pre-flight block rate indicates brand terminology guidelines may benefit from upstream briefing sessions for creative contributors."
        )
    if top_recurring and top_recurring[0].category == "TERMINOLOGY":
        inferred.append(
            f"Creators frequently use superseded terminology flagged by '{top_recurring[0].rule_code}'; consider distributing a quick-reference brand terminology cheat-sheet."
        )
    if top_recurring and any(t.category == "FACTUAL" for t in top_recurring):
        inferred.append(
            "Factual claim unverified warnings detected; consider expanding approved brand memory reference facts to cover emerging campaign topics."
        )
    if total_sugg > 0 and adoption_rate_pct >= 80.0:
        inferred.append(
            "High remediation adoption demonstrates high creator confidence in surgical auto-correction suggestions."
        )
    elif total_sugg > 0 and adoption_rate_pct < 50.0:
        inferred.append(
            "Remediation adoption is below 50%; review suggestion quality and contextual fit to avoid friction."
        )

    if not inferred:
        inferred.append("Brand compliance metrics are within healthy operational thresholds.")

    return LongitudinalInsightsResponse(
        workspace_id=workspace_id,
        client_id=client_id,
        period_days=period_days,
        total_audits=total_audits,
        pass_rate_pct=pass_rate_pct,
        block_rate_pct=block_rate_pct,
        warnings_rate_pct=warnings_rate_pct,
        remediation_adoption=remediation_stat,
        top_recurring_violations=top_recurring[:10],
        temporal_trends=temporal_trends,
        observed_insights=observed,
        inferred_recommendations=inferred,
    )

