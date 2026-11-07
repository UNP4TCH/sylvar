"""Candidate rule extraction engine (TASK-017).

Extracts brand rules in 4 canonical categories:
- TERMINOLOGY: Prohibited/mandatory terms, case sensitivity, severity, exceptions.
- FACT: Verified reference statements for NLI grounding.
- COLOR: Hex codes, color names, tolerances.
- VOICE: Tone and communication guardrails.
"""
import logging
import re
from typing import Any

from app.models.document import RuleCategory
from app.modules.documents.parser import ParsedSection

logger = logging.getLogger("sylvar.documents.extractor")


def extract_candidate_rules_deterministic(sections: list[ParsedSection]) -> list[dict[str, Any]]:
    """Extract candidate rules using deterministic pattern heuristics (offline fallback)."""
    candidates: list[dict[str, Any]] = []

    full_text = "\n\n".join(s.content for s in sections)
    lines = [line.strip() for line in full_text.splitlines() if line.strip()]

    # 1. Terminology extraction: look for "Do not use", "Never say", "Forbidden:", "Prohibited:"
    term_pattern = re.compile(
        r"(?:never\s+use|do\s+not\s+use|avoid|prohibited\s+term[s]?:|forbidden:)\s*(?:['\"]([^'\"]+)['\"]|([a-zA-Z0-9_-]+))(?:[;,]?\s*(?:instead\s+use|prefer|use)\s*(?:['\"]([^'\"]+)['\"]|([a-zA-Z0-9_-]+)))?",
        re.IGNORECASE,
    )

    for line in lines:
        match = term_pattern.search(line)
        if match:
            prohibited = (match.group(1) or match.group(2)).strip()
            replacement = (
                (match.group(3) or match.group(4)).strip()
                if (match.group(3) or match.group(4))
                else None
            )
            candidates.append(
                {
                    "category": RuleCategory.TERMINOLOGY.value,
                    "payload": {
                        "term": prohibited,
                        "preferred_alternative": replacement,
                        "replacement": replacement,
                        "severity": "CRITICAL",
                        "case_sensitive": False,
                        "rationale": line,
                    },
                }
            )

    # 2. Color extraction: look for hex codes (#RRGGBB or #RGB)
    hex_pattern = re.compile(r"(#([0-9a-fA-F]{3}|[0-9a-fA-F]{6}))\b")
    for line in lines:
        for match in hex_pattern.finditer(line):
            hex_code = match.group(1).upper()
            candidates.append(
                {
                    "category": RuleCategory.COLOR.value,
                    "payload": {
                        "hex_code": hex_code,
                        "delta_e_threshold": 5.0,
                        "severity": "ADVISORY",  # Visual deviations are always advisory per ADR-008
                        "context": line,
                    },
                }
            )

    # 3. Factual extraction: statements declaring certifications, uptime, metrics, guarantees, ingredients
    fact_pattern = re.compile(
        r"(guarantee[s]?|certifi[ed|cation]|uptime|headquarters|founded\s+in|sla\s+of|compliance|organic|vegan|cruelty-free|factual:?)\b",
        re.IGNORECASE,
    )
    for line in lines:
        if fact_pattern.search(line) and len(line) > 10:
            candidates.append(
                {
                    "category": RuleCategory.FACT.value,
                    "payload": {
                        "claim_fact": line,
                        "statement": line,
                        "severity": "CRITICAL",
                        "verification_type": "EXACT_GROUNDING",
                    },
                }
            )

    # If no specific patterns matched, generate default baseline candidates from section headings
    if not candidates:
        for sec in sections[:3]:
            candidates.append(
                {
                    "category": RuleCategory.VOICE.value,
                    "payload": {
                        "guideline": sec.content[:200],
                        "heading": sec.heading or "General Guidance",
                        "severity": "ADVISORY",
                    },
                }
            )

    return candidates


def extract_candidate_rules(
    sections: list[ParsedSection],
    api_key: str | None = None,
    model: str = "VERIFY_BEFORE_SELECTING",
) -> list[dict[str, Any]]:
    """Extract candidate rules from parsed document sections.

    Uses live Gemini API when api_key is present.
    On failure or when api_key is None, seamlessly executes deterministic pattern heuristics.
    """
    if api_key and api_key != "CHANGE_ME":
        try:
            from app.modules.documents.gemini_extractor import extract_candidate_rules_with_gemini

            gemini_candidates = extract_candidate_rules_with_gemini(
                sections, api_key=api_key, model=model
            )
            if gemini_candidates:
                return gemini_candidates
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "Gemini rule extraction failed or timed out: %s. Falling back to deterministic heuristics.",
                e,
            )

    return extract_candidate_rules_deterministic(sections)


async def async_extract_candidate_rules(
    sections: list[ParsedSection],
    api_key: str | None = None,
    model: str = "VERIFY_BEFORE_SELECTING",
) -> list[dict[str, Any]]:
    """Asynchronous candidate rule extraction using background thread pool (M-06)."""
    if api_key and api_key != "CHANGE_ME":
        try:
            from app.modules.documents.gemini_extractor import (
                async_extract_candidate_rules_with_gemini,
            )

            gemini_candidates = await async_extract_candidate_rules_with_gemini(
                sections, api_key=api_key, model=model
            )
            if gemini_candidates:
                return gemini_candidates
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "Gemini rule extraction failed or timed out: %s. Falling back to deterministic heuristics.",
                e,
            )

    return extract_candidate_rules_deterministic(sections)
