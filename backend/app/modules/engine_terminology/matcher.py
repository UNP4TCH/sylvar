"""Terminology Compliance Engine (TASK-022).

Deterministic regex engine with Unicode NFC normalization, exact character offset span extraction,
case sensitivity support, exception lists, and surgical correction proposals.
"""
import re
import unicodedata
from dataclasses import dataclass
from typing import Any


@dataclass
class TerminologyFinding:
    rule_id: str | None
    rule_code: str
    severity: str
    message: str
    location_start: int
    location_end: int
    snippet: str
    original_text: str
    suggested_text: str | None
    rationale: str
    evidence: dict[str, Any]


def run_terminology_check(
    text: str, rules: list[dict[str, Any]]
) -> tuple[str, list[TerminologyFinding]]:
    """Execute terminology check against approved brand terminology rules.

    Returns:
        (check_status: "PASS" | "WARNING" | "FAIL", findings: list[TerminologyFinding])
    """
    if not text.strip():
        return "PASS", []

    # Unicode NFC Normalization
    normalized_text = unicodedata.normalize("NFC", text)
    findings: list[TerminologyFinding] = []

    for rule in rules:
        if rule.get("category") != "TERMINOLOGY":
            continue

        content = rule.get("content", {})
        raw_forbidden = content.get("forbidden_term") or content.get("term")
        if not raw_forbidden:
            continue

        # Unicode NFC normalization on term (M-11)
        norm_term = unicodedata.normalize("NFC", str(raw_forbidden)).strip()
        if not norm_term:
            continue

        replacement = (
            content.get("replacement")
            or content.get("preferred")
            or content.get("preferred_alternative")
        )
        case_sensitive = content.get("case_sensitive", False)
        raw_sev = content.get("severity", "MAJOR")
        severity = "CRITICAL" if raw_sev in ("BLOCKING", "CRITICAL") else raw_sev
        exceptions = content.get("exceptions", [])
        rule_code = rule.get("rule_code", "RULE-TERM")
        rule_id = rule.get("rule_id")

        # Compile Unicode-aware lookaround boundary pattern (M-11)
        flags = 0 if case_sensitive else re.IGNORECASE
        escaped_term = re.escape(norm_term)
        prefix_bound = r"(?<!\w)" if norm_term[0].isalnum() else ""
        suffix_bound = r"(?!\w)" if norm_term[-1].isalnum() else ""
        pattern = re.compile(rf"{prefix_bound}{escaped_term}{suffix_bound}", flags)

        for match in pattern.finditer(normalized_text):
            start = match.start()
            end = match.end()
            matched_text = match.group(0)

            # Check if match falls within an exception
            is_exception = False
            for exc in exceptions:
                if exc.lower() in normalized_text[max(0, start - 20) : min(len(normalized_text), end + 20)].lower():
                    is_exception = True
                    break
            if is_exception:
                continue

            # Context snippet (up to 30 chars before and after)
            ctx_start = max(0, start - 30)
            ctx_end = min(len(normalized_text), end + 30)
            snippet = normalized_text[ctx_start:ctx_end]

            msg = f"Forbidden term '{matched_text}' detected."
            if replacement:
                msg += f" Brand guidelines require using '{replacement}' instead."

            findings.append(
                TerminologyFinding(
                    rule_id=rule_id,
                    rule_code=rule_code,
                    severity=severity,
                    message=msg,
                    location_start=start,
                    location_end=end,
                    snippet=snippet,
                    original_text=matched_text,
                    suggested_text=replacement,
                    rationale=f"Rule {rule_code}: Do not use '{norm_term}'.",
                    evidence={
                        "forbidden_term": norm_term,
                        "matched_term": matched_text,
                        "replacement": replacement,
                        "case_sensitive": case_sensitive,
                    },
                )
            )

    # -------------------------------------------------------------------------
    # Brand Rules & Tone / Voice Guidelines
    # -------------------------------------------------------------------------
    for rule in rules:
        if rule.get("category") != "VOICE":
            continue
        content = rule.get("content", {})
        guideline_text = content.get("guideline", "") or content.get("heading", "")
        rule_code = rule.get("rule_code", "RULE-VOICE")
        rule_id = rule.get("rule_id")

        # Check for tone / voice forbidden keywords if specified
        tone_forbidden = content.get("forbidden_terms") or []
        for raw_term in tone_forbidden:
            norm_term = unicodedata.normalize("NFC", str(raw_term)).strip()
            if not norm_term:
                continue
            for m in re.finditer(rf"\b{re.escape(norm_term)}\b", normalized_text, re.IGNORECASE):
                ctx_s = max(0, m.start() - 30)
                ctx_e = min(len(normalized_text), m.end() + 30)
                findings.append(
                    TerminologyFinding(
                        rule_id=rule_id,
                        rule_code=rule_code,
                        severity=content.get("severity", "ADVISORY"),
                        message=f"Tone/voice guideline violation: '{m.group(0)}' conflicts with brand voice standards.",
                        location_start=m.start(),
                        location_end=m.end(),
                        snippet=normalized_text[ctx_s:ctx_e],
                        original_text=m.group(0),
                        suggested_text=None,
                        rationale=f"Brand Voice Guideline: {guideline_text or 'Align with brand voice.'}",
                        evidence={"guideline": guideline_text, "matched_tone_term": m.group(0)},
                    )
                )

    # -------------------------------------------------------------------------
    # Deterministic Accessibility & Tone Consistency Heuristics
    # -------------------------------------------------------------------------
    # 1. Generic nondescript hyperlinks (WCAG 2.4.4 Link Purpose)
    generic_links = [r"\bclick here\b", r"\btap here\b", r"\bread more\b", r"\bclick this link\b"]
    for link_pattern in generic_links:
        for m in re.finditer(link_pattern, normalized_text, re.IGNORECASE):
            ctx_s = max(0, m.start() - 25)
            ctx_e = min(len(normalized_text), m.end() + 25)
            findings.append(
                TerminologyFinding(
                    rule_id=None,
                    rule_code="ACCESSIBILITY-WCAG-LINK",
                    severity="ADVISORY",
                    message="Nondescript link text detected. Links should describe their specific destination for screen readers.",
                    location_start=m.start(),
                    location_end=m.end(),
                    snippet=normalized_text[ctx_s:ctx_e],
                    original_text=m.group(0),
                    suggested_text="explore our curated product catalog",
                    rationale="WCAG 2.4.4: Link purpose must be clear from link text alone to support screen readers and assistive tech.",
                    evidence={"wcag_criterion": "2.4.4", "matched_text": m.group(0)},
                )
            )

    # 2. Exaggerated / Sensationalist punctuation (!!+, ???+)
    for m in re.finditer(r"([!]{2,}|\?{2,})", normalized_text):
        ctx_s = max(0, m.start() - 25)
        ctx_e = min(len(normalized_text), m.end() + 25)
        clean_punct = m.group(0)[0]
        findings.append(
            TerminologyFinding(
                rule_id=None,
                rule_code="VOICE-PUNCTUATION",
                severity="ADVISORY",
                message="Sensationalist repeated punctuation detected. Brand tone guidelines require polished, restrained punctuation.",
                location_start=m.start(),
                location_end=m.end(),
                snippet=normalized_text[ctx_s:ctx_e],
                original_text=m.group(0),
                suggested_text=clean_punct,
                rationale="Brand Voice Standards: Avoid repeated exclamation or question marks in professional copy.",
                evidence={"repeated_punctuation": m.group(0)},
            )
        )

    # 3. All-caps shouting words (>4 consecutive uppercase letters, excluding standard acronyms)
    standard_acronyms = {"SPF", "UVA", "UVB", "HTML", "JSON", "SHA", "NFC", "USA", "FDA", "OECD", "GMP", "ISO", "API"}
    for m in re.finditer(r"\b[A-Z]{5,}\b", normalized_text):
        word = m.group(0)
        if word in standard_acronyms:
            continue
        ctx_s = max(0, m.start() - 20)
        ctx_e = min(len(normalized_text), m.end() + 20)
        findings.append(
            TerminologyFinding(
                rule_id=None,
                rule_code="ACCESSIBILITY-READABILITY",
                severity="ADVISORY",
                message=f"All-caps word '{word}' detected. May be read as an acronym by screen readers and impairs reading comprehension.",
                location_start=m.start(),
                location_end=m.end(),
                snippet=normalized_text[ctx_s:ctx_e],
                original_text=word,
                suggested_text=word.title(),
                rationale="WCAG & Brand Tone: Use title or sentence case for regular emphasis instead of all-caps.",
                evidence={"all_caps_word": word},
            )
        )

    has_critical = any(f.severity == "CRITICAL" for f in findings)
    has_major = any(f.severity in ("MAJOR", "MINOR") for f in findings)

    if has_critical:
        status = "FAIL"
    elif has_major:
        status = "WARNING"
    else:
        status = "PASS"

    return status, findings
