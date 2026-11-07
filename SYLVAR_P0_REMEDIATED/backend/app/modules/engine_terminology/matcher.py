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

    has_critical = any(f.severity == "CRITICAL" for f in findings)
    has_major = any(f.severity in ("MAJOR", "MINOR") for f in findings)

    if has_critical:
        status = "FAIL"
    elif has_major:
        status = "WARNING"
    else:
        status = "PASS"

    return status, findings
