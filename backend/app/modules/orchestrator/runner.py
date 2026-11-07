"""Audit Orchestrator (TASK-021).

Coordinates concurrent execution of:
- Terminology Engine (deterministic regex, NFC normalization)
- Factual Verification Engine (epistemic tri-state: SUPPORTED / CONTRADICTED / UNVERIFIED)
- Visual Compliance Engine (pure Python CIEDE2000 linear-light advisory check)

Aggregates findings into the Diagnostic Scorecard (BLOCKED, WARNINGS, PASS).
Generates actionable surgical correction proposals.
"""
import asyncio
import logging
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.audit import (
    AuditCheck,
    AuditFinding,
    AuditRun,
    AuditRunStatus,
    AuditVerdict,
    CheckStatus,
    CorrectionSuggestion,
    EngineType,
)
from app.modules.engine_factual.verifier import run_async_factual_check
from app.modules.engine_terminology.matcher import run_terminology_check
from app.modules.engine_visual.analyzer import run_visual_check

logger = logging.getLogger("sylvar.orchestrator")


async def execute_audit(
    workspace_id: uuid.UUID,
    client_id: uuid.UUID,
    asset_id: uuid.UUID,
    asset_version_id: uuid.UUID,
    snapshot_id: uuid.UUID,
    rules: list[dict[str, Any]],
    text_content: str | None,
    image_bytes: bytes | None,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> AuditRun:
    """Run full pre-publication audit against compiled brand memory snapshot."""
    # 1. Create AuditRun record
    audit_run = AuditRun(
        workspace_id=workspace_id,
        client_id=client_id,
        asset_id=asset_id,
        asset_version_id=asset_version_id,
        snapshot_id=snapshot_id,
        status=AuditRunStatus.RUNNING.value,
        triggered_by_user_id=user_id,
    )
    db.add(audit_run)
    await db.flush()

    # 2. Prepare concurrent engine tasks
    async def _execute_terminology() -> tuple[str, int, list[Any], dict[str, Any]]:
        t0 = time.perf_counter()
        if not text_content or not text_content.strip():
            return "FAIL", 0, [], {"skipped": True, "reason": "Required text content is missing."}
        status, findings = run_terminology_check(text_content, rules)
        duration_ms = int((time.perf_counter() - t0) * 1000)
        return status, duration_ms, findings, {"matched_count": len(findings)}

    async def _execute_factual() -> tuple[str, int, list[Any], dict[str, Any]]:
        t0 = time.perf_counter()
        if not text_content or not text_content.strip():
            return "FAIL", 0, [], {"skipped": True, "reason": "Required text content is missing."}
        settings = get_settings()
        status, findings, details = await run_async_factual_check(
            text_content, rules, api_key=settings.gemini_api_key, model=settings.gemini_model
        )
        duration_ms = int((time.perf_counter() - t0) * 1000)
        return status, duration_ms, findings, details

    async def _execute_visual() -> tuple[str, int, list[Any], dict[str, Any]]:
        t0 = time.perf_counter()
        if not image_bytes:
            return "PASS", 0, [], {
                "skipped": True,
                "reason": "MVP supports TEXT assets only; image auditing is not available.",
            }
        status, findings = run_visual_check(image_bytes, rules)
        duration_ms = int((time.perf_counter() - t0) * 1000)
        return status, duration_ms, findings, {"advisory_count": len(findings)}

    # 3. Concurrently execute with exception isolation
    results = await asyncio.gather(
        _execute_terminology(),
        _execute_factual(),
        _execute_visual(),
        return_exceptions=True,
    )

    all_findings_severities: list[str] = []
    engine_failure = False
    failure_errors: list[str] = []

    # 4. Process Terminology Engine Results
    term_res = results[0]
    if isinstance(term_res, BaseException):
        logger.exception("Terminology engine internal error: %s", term_res)
        engine_failure = True
        failure_errors.append("Terminology compliance engine encountered an internal execution error.")
        all_findings_severities.append("CRITICAL")
        check_term = AuditCheck(
            workspace_id=workspace_id,
            client_id=client_id,
            audit_run_id=audit_run.id,
            engine_type=EngineType.TERMINOLOGY.value,
            status=CheckStatus.FAIL.value,
            execution_time_ms=0,
            summary_details={"error": "Terminology compliance engine encountered an internal execution error."},
        )
        db.add(check_term)
        await db.flush()
        db.add(
            AuditFinding(
                workspace_id=workspace_id,
                client_id=client_id,
                audit_run_id=audit_run.id,
                check_id=check_term.id,
                rule_code="ENGINE-FAIL-TERMINOLOGY",
                severity="CRITICAL",
                message="Terminology compliance engine encountered an internal execution error.",
                evidence={"error_code": "INTERNAL_ENGINE_ERROR"},
            )
        )
    else:
        status, duration_ms, term_findings, details = term_res
        check_term = AuditCheck(
            workspace_id=workspace_id,
            client_id=client_id,
            audit_run_id=audit_run.id,
            engine_type=EngineType.TERMINOLOGY.value,
            status=status,
            execution_time_ms=duration_ms,
            summary_details=details,
        )
        db.add(check_term)
        await db.flush()

        for f in term_findings:
            all_findings_severities.append(f.severity)
            finding = AuditFinding(
                workspace_id=workspace_id,
                client_id=client_id,
                audit_run_id=audit_run.id,
                check_id=check_term.id,
                rule_id=uuid.UUID(f.rule_id) if f.rule_id else None,
                rule_code=f.rule_code,
                severity=f.severity,
                message=f.message,
                location_start=f.location_start,
                location_end=f.location_end,
                snippet=f.snippet,
                evidence=f.evidence,
            )
            db.add(finding)
            await db.flush()

            if f.suggested_text:
                sugg = CorrectionSuggestion(
                    workspace_id=workspace_id,
                    client_id=client_id,
                    audit_run_id=audit_run.id,
                    finding_id=finding.id,
                    original_text=f.original_text,
                    suggested_text=f.suggested_text,
                    rationale=f.rationale,
                )
                db.add(sugg)

    # 5. Process Factual Engine Results
    fact_res = results[1]
    is_factual_offline_demo = False
    if isinstance(fact_res, BaseException):
        logger.exception("Factual verification engine internal error: %s", fact_res)
        engine_failure = True
        failure_errors.append("Factual verification engine encountered an internal execution error.")
        all_findings_severities.append("CRITICAL")
        check_fact = AuditCheck(
            workspace_id=workspace_id,
            client_id=client_id,
            audit_run_id=audit_run.id,
            engine_type=EngineType.FACTUAL.value,
            status=CheckStatus.FAIL.value,
            execution_time_ms=0,
            summary_details={"error": "Factual verification engine encountered an internal execution error."},
        )
        db.add(check_fact)
        await db.flush()
        db.add(
            AuditFinding(
                workspace_id=workspace_id,
                client_id=client_id,
                audit_run_id=audit_run.id,
                check_id=check_fact.id,
                rule_code="ENGINE-FAIL-FACTUAL",
                severity="CRITICAL",
                message="Factual verification engine encountered an internal execution error.",
                evidence={"error_code": "INTERNAL_ENGINE_ERROR"},
            )
        )
    else:
        status, duration_ms, fact_findings, details = fact_res
        settings = get_settings()
        is_live_gemini = details.get("engine_mode") == "gemini_live" and not details.get("provider_error")

        if not is_live_gemini:
            if settings.allow_offline_demo:
                is_factual_offline_demo = True
                details["demo_mode"] = True
                details["demo_warning"] = (
                    "DEMO ONLY: Factual verification was performed in offline heuristic mode. "
                    "Claims remain UNVERIFIED and not certified for production."
                )
            else:
                engine_failure = True
                failure_errors.append(details.get("reason") or "Live factual verification did not complete.")

        check_fact = AuditCheck(
            workspace_id=workspace_id,
            client_id=client_id,
            audit_run_id=audit_run.id,
            engine_type=EngineType.FACTUAL.value,
            status=status,
            execution_time_ms=duration_ms,
            summary_details=details,
        )
        db.add(check_fact)
        await db.flush()

        for f in fact_findings:
            all_findings_severities.append(f.severity)
            finding = AuditFinding(
                workspace_id=workspace_id,
                client_id=client_id,
                audit_run_id=audit_run.id,
                check_id=check_fact.id,
                rule_id=uuid.UUID(f.rule_id) if f.rule_id else None,
                rule_code=f.rule_code,
                severity=f.severity,
                message=f.message,
                location_start=f.location_start,
                location_end=f.location_end,
                snippet=f.snippet,
                evidence=f.evidence,
            )
            db.add(finding)
            await db.flush()

            if f.suggested_correction:
                sugg = CorrectionSuggestion(
                    workspace_id=workspace_id,
                    client_id=client_id,
                    audit_run_id=audit_run.id,
                    finding_id=finding.id,
                    original_text=f.original_claim,
                    suggested_text=f.suggested_correction,
                    rationale=f.rationale,
                )
                db.add(sugg)

    # 6. Process Visual Engine Results
    vis_res = results[2]
    if isinstance(vis_res, BaseException):
        logger.exception("Visual compliance engine internal error: %s", vis_res)
        engine_failure = True
        failure_errors.append("Visual compliance engine encountered an internal execution error.")
        all_findings_severities.append("CRITICAL")
        check_vis = AuditCheck(
            workspace_id=workspace_id,
            client_id=client_id,
            audit_run_id=audit_run.id,
            engine_type=EngineType.VISUAL.value,
            status=CheckStatus.FAIL.value,
            execution_time_ms=0,
            summary_details={"error": "Visual compliance engine encountered an internal execution error."},
        )
        db.add(check_vis)
        await db.flush()
        db.add(
            AuditFinding(
                workspace_id=workspace_id,
                client_id=client_id,
                audit_run_id=audit_run.id,
                check_id=check_vis.id,
                rule_code="ENGINE-FAIL-VISUAL",
                severity="CRITICAL",
                message="Visual compliance engine encountered an internal execution error.",
                evidence={"error_code": "INTERNAL_ENGINE_ERROR"},
            )
        )
    else:
        status, duration_ms, vis_findings, details = vis_res
        check_vis = AuditCheck(
            workspace_id=workspace_id,
            client_id=client_id,
            audit_run_id=audit_run.id,
            engine_type=EngineType.VISUAL.value,
            status=status if status in ("PASS", "WARNING", "FAIL") else "PASS",
            execution_time_ms=duration_ms,
            summary_details=details,
        )
        db.add(check_vis)
        await db.flush()

        for f in vis_findings:
            all_findings_severities.append(f.severity)
            finding = AuditFinding(
                workspace_id=workspace_id,
                client_id=client_id,
                audit_run_id=audit_run.id,
                check_id=check_vis.id,
                rule_id=uuid.UUID(f.rule_id) if f.rule_id else None,
                rule_code=f.rule_code,
                severity=f.severity,
                message=f.message,
                evidence=f.evidence,
            )
            db.add(finding)

    # 7. Diagnostic Scorecard Overall Verdict (Resolves C-05: Engine failure prevents PASS)
    if engine_failure:
        audit_run.status = AuditRunStatus.FAILED.value
        verdict = AuditVerdict.BLOCKED.value
        audit_run.error_details = "; ".join(failure_errors) if failure_errors else "Audit engine failure detected."
    elif "CRITICAL" in all_findings_severities:
        audit_run.status = AuditRunStatus.COMPLETED.value
        verdict = AuditVerdict.BLOCKED.value
        if is_factual_offline_demo:
            audit_run.error_details = (
                "DEMO MODE: Critical deterministic violations detected. Factual verification remains unverified."
            )
    elif is_factual_offline_demo:
        # Factual verification remains UNVERIFIED in demo mode; overall verdict is WARNINGS (never PASS)
        audit_run.status = AuditRunStatus.COMPLETED.value
        verdict = AuditVerdict.WARNINGS.value
        audit_run.error_details = (
            "DEMO MODE: Factual verification was unavailable and remains UNVERIFIED. "
            "Content may be submitted for human review under demo policy only."
        )
    elif any(s in ("MAJOR", "MINOR") for s in all_findings_severities):
        audit_run.status = AuditRunStatus.COMPLETED.value
        verdict = AuditVerdict.WARNINGS.value
    else:
        audit_run.status = AuditRunStatus.COMPLETED.value
        verdict = AuditVerdict.PASS.value

    audit_run.overall_verdict = verdict
    audit_run.completed_at = datetime.now(UTC)
    await db.flush()

    return audit_run
