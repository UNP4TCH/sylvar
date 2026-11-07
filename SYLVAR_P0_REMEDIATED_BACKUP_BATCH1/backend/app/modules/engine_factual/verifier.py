"""Factual Verification Engine (TASK-023).

Adheres to ADR-005 (Epistemic Tri-State Factual Verification):
- SUPPORTED: Claim is directly verified and grounded in an approved brand fact.
- CONTRADICTED: Claim explicitly contradicts an approved brand fact.
- UNVERIFIED: Claim asserts brand credentials/facts not found in approved memory (unverified != false).
- Verbatim substring citation assertion from knowledge snapshot.
- Seamlessly delegates to Gemini Live API when API key is provided, with deterministic offline fallback.
"""
import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("sylvar.factual")


@dataclass
class FactualFinding:
    rule_id: str | None
    rule_code: str
    severity: str
    message: str
    location_start: int | None
    location_end: int | None
    snippet: str
    verdict: str  # SUPPORTED, CONTRADICTED, UNVERIFIED
    original_claim: str
    suggested_correction: str | None
    rationale: str
    evidence: dict[str, Any]


def extract_sentences(text: str) -> list[tuple[str, int, int]]:
    """Extract sentences with character offsets."""
    sentences = []
    # Match sentences ending with . ! ? or linebreaks
    for match in re.finditer(r"([^.!?\n]+[.!?]?)", text):
        raw = match.group(0).strip()
        if len(raw) > 5:
            start = match.start()
            end = match.end()
            sentences.append((raw, start, end))
    return sentences


def run_deterministic_factual_check(
    text: str, rules: list[dict[str, Any]]
) -> tuple[str, list[FactualFinding]]:
    """Deterministic offline NLP heuristic verifier for test suites and offline operation."""
    if not text.strip():
        return "PASS", []

    fact_rules = [r for r in rules if r.get("category") == "FACT"]
    sentences = extract_sentences(text)
    findings: list[FactualFinding] = []

    # Tokenize fact statements for semantic overlap checks
    for sent, start, end in sentences:
        sent_lower = sent.lower()

        # Check against each fact rule
        for rule in fact_rules:
            content = rule.get("content", {})
            fact_statement = content.get("statement") or content.get("claim_fact", "")
            if not fact_statement:
                continue

            rule_code = rule.get("rule_code", "RULE-FACT")
            rule_id = rule.get("rule_id")
            fact_lower = fact_statement.lower()

            # Check for direct contradictions:
            contradiction_pairs = [
                ("vegan", "not vegan"),
                ("vegan", "animal"),
                ("organic", "synthetic"),
                ("organic", "not organic"),
                ("cruelty-free", "tested on animals"),
                ("handmade", "mass-produced"),
                ("sugar-free", "contains sugar"),
                ("paraben-free", "contains parabens"),
            ]

            contradicted = False
            for positive, negative in contradiction_pairs:
                if positive in fact_lower and negative in sent_lower:
                    contradicted = True
                    break
                if negative in fact_lower and positive in sent_lower:
                    contradicted = True
                    break

            if contradicted:
                findings.append(
                    FactualFinding(
                        rule_id=str(rule_id) if rule_id else None,
                        rule_code=rule_code,
                        severity="CRITICAL",
                        message=f"Claim contradicts approved brand fact: '{fact_statement}'",
                        location_start=start,
                        location_end=end,
                        snippet=sent,
                        verdict="CONTRADICTED",
                        original_claim=sent,
                        suggested_correction=f"Align statement with brand fact: '{fact_statement}'",
                        rationale=f"Contradiction detected against {rule_code}.",
                        evidence={
                            "approved_fact": fact_statement,
                            "contested_claim": sent,
                            "verdict": "CONTRADICTED",
                            "citation": fact_statement,  # Verbatim substring from memory
                        },
                    )
                )

    # Check for unverified high-stakes brand claims
    unverified_claim_keywords = [
        "clinically proven",
        "cure",
        "100% guarantee",
        "miracle",
        "patented",
        "doctor recommended",
        "#1 brand",
    ]

    all_facts_text = " ".join(
        (r.get("content", {}).get("statement", "")).lower() for r in fact_rules
    )

    for sent, start, end in sentences:
        sent_lower = sent.lower()
        for kw in unverified_claim_keywords:
            if kw in sent_lower and kw not in all_facts_text:
                findings.append(
                    FactualFinding(
                        rule_id=None,
                        rule_code="FACT-UNVERIFIED",
                        severity="MAJOR",
                        message=f"Unverified high-stakes factual claim '{kw}' is not supported by approved brand facts.",
                        location_start=start,
                        location_end=end,
                        snippet=sent,
                        verdict="UNVERIFIED",
                        original_claim=sent,
                        suggested_correction=f"Remove or substantiate '{kw}' with verified documentation.",
                        rationale="ADR-005: Unverified claims require explicit substantiation.",
                        evidence={
                            "unverified_keyword": kw,
                            "claim_snippet": sent,
                            "verdict": "UNVERIFIED",
                        },
                    )
                )
                break

    has_critical = any(f.severity == "CRITICAL" for f in findings)
    has_major = any(f.severity in ("MAJOR", "MINOR") for f in findings)

    if has_critical:
        status = "FAIL"
    elif has_major:
        status = "WARNING"
    else:
        status = "PASS"

    return status, findings


def run_factual_check(
    text: str,
    rules: list[dict[str, Any]],
    api_key: str | None = None,
    model: str = "VERIFY_BEFORE_SELECTING",
) -> tuple[str, list[FactualFinding]]:
    """Synchronous facade for factual check (used by sync tests and offline execution)."""
    if api_key and api_key != "CHANGE_ME":
        try:
            from app.modules.engine_factual.gemini_verifier import verify_facts_with_gemini

            return verify_facts_with_gemini(text, rules, api_key=api_key, model=model)
        except Exception as e:  # noqa: BLE001
            logger.error("Gemini live factual verification failed: %s", e)
            return "FAIL", [
                FactualFinding(
                    rule_id=None,
                    rule_code="GEMINI-ERROR",
                    severity="CRITICAL",
                    message=f"Gemini live factual verification failed: {e}",
                    location_start=None,
                    location_end=None,
                    snippet="",
                    verdict="UNVERIFIED",
                    original_claim="",
                    suggested_correction=None,
                    rationale=f"AI provider failure: {e}",
                    evidence={"provider_error": str(e), "engine_mode": "gemini_live"},
                )
            ]

    # Offline heuristics are useful for triage, but cannot establish factual
    # compliance. Never let their clean result become an authoritative PASS.
    _heuristic_status, heuristic_findings = run_deterministic_factual_check(text, rules)
    if not heuristic_findings:
        heuristic_findings = [
            FactualFinding(
                rule_id=None,
                rule_code="FACTUAL-UNVERIFIED-OFFLINE",
                severity="CRITICAL",
                message="Factual verification was unavailable; offline heuristics cannot certify this content.",
                location_start=None,
                location_end=None,
                snippet="",
                verdict="UNVERIFIED",
                original_claim="",
                suggested_correction=None,
                rationale="A live factual verifier is required for an authoritative compliance result.",
                evidence={"engine_mode": "offline_heuristic", "reason": "LIVE_VERIFIER_UNAVAILABLE"},
            )
        ]
    return "FAIL", heuristic_findings


async def run_async_factual_check(
    text: str,
    rules: list[dict[str, Any]],
    api_key: str | None = None,
    model: str = "VERIFY_BEFORE_SELECTING",
) -> tuple[str, list[FactualFinding], dict[str, Any]]:
    """Asynchronous factual verification executing in background thread to avoid event-loop blocking (M-06).

    Preserves C-06 integrity: distinguishes provider success, deterministic fallback, and failure.
    """
    if api_key and api_key != "CHANGE_ME":
        try:
            from app.modules.engine_factual.gemini_verifier import verify_facts_with_gemini

            status, findings = await asyncio.to_thread(
                verify_facts_with_gemini, text, rules, api_key=api_key, model=model
            )
            return status, findings, {
                "engine_mode": "gemini_live",
                "model": model,
                "checked_count": len(findings),
            }
        except Exception as e:  # noqa: BLE001
            logger.error("Gemini live verification failed: %s", e)
            findings = [
                FactualFinding(
                    rule_id=None,
                    rule_code="GEMINI-ERROR",
                    severity="CRITICAL",
                    message=f"Gemini live factual verification failed: {e}",
                    location_start=None,
                    location_end=None,
                    snippet="",
                    verdict="UNVERIFIED",
                    original_claim="",
                    suggested_correction=None,
                    rationale=f"AI provider failure: {e}",
                    evidence={"provider_error": str(e), "engine_mode": "gemini_live"},
                )
            ]
            return "FAIL", findings, {
                "engine_mode": "gemini_live",
                "model": model,
                "provider_error": str(e),
                "status": "FAIL",
            }

    # Deterministic offline mode is advisory only. It may surface obvious issues,
    # but it cannot establish completeness or authorize a compliance PASS.
    _heuristic_status, findings = run_deterministic_factual_check(text, rules)
    return "FAIL", findings, {
        "engine_mode": "deterministic_offline",
        "checked_count": len(findings),
        "authoritative": False,
        "reason": "Live factual verification is not configured; publication must remain blocked.",
    }
