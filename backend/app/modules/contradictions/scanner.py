"""Guideline Contradiction Detection Engine (TASK-022 / Stage 3 Differentiator).

Adheres to:
- Deterministic cross-rule analysis for Terminology, Color, and Factual guidelines.
- Returns explicit source passages and rule codes.
- Human resolution accountability: never silently resolves or rewrites guidelines.
"""
import hashlib
import re
from typing import Any

from app.modules.contradictions.schemas import ContradictionItem, RuleExcerpt
from app.modules.engine_visual.analyzer import ciede2000, hex_to_rgb, rgb_to_lab


def _generate_conflict_id(id_a: str, id_b: str) -> str:
    """Generate deterministic conflict ID from pair of rule IDs."""
    sorted_ids = sorted([str(id_a), str(id_b)])
    combined = f"{sorted_ids[0]}:{sorted_ids[1]}"
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()[:16]


def _normalize_category(cat: Any) -> str:
    """Normalize rule category enum or string to standardized uppercase token."""
    if hasattr(cat, "value"):
        s = str(cat.value)
    else:
        s = str(cat)
    if "." in s:
        s = s.split(".")[-1]
    return s.upper()


def _extract_term(val: Any) -> str:
    """Extract string term from string or single-item list."""
    if isinstance(val, list) and val:
        return str(val[0]).strip().lower()
    if isinstance(val, str):
        return val.strip().lower()
    return ""


def _make_excerpt(rule: dict[str, Any]) -> RuleExcerpt:
    content = rule.get("content", {})
    stmt = (
        content.get("statement")
        or content.get("rule_statement")
        or content.get("claim_fact")
        or content.get("name")
        or content.get("context")
        or str(content)
    )
    return RuleExcerpt(
        rule_id=str(rule.get("rule_id", "")),
        rule_code=rule.get("rule_code", "RULE"),
        category=_normalize_category(rule.get("category", "UNKNOWN")),
        statement=stmt,
        forbidden_term=content.get("forbidden_term") or content.get("term"),
        preferred_term=content.get("preferred_term") or content.get("replacement") or content.get("preferred_alternative"),
        hex_code=content.get("hex") or content.get("hex_code"),
        source_document=rule.get("source_document") or content.get("source_document"),
        section=rule.get("section") or content.get("section"),
    )


def scan_for_contradictions(rules: list[dict[str, Any]]) -> list[ContradictionItem]:
    """Scan an arbitrary list of rules and return all detected guideline contradictions."""
    contradictions: list[ContradictionItem] = []
    n = len(rules)

    for i in range(n):
        for j in range(i + 1, n):
            r1, r2 = rules[i], rules[j]
            cat1 = _normalize_category(r1.get("category"))
            cat2 = _normalize_category(r2.get("category"))

            # 1. Terminology Contradictions
            if cat1 == "TERMINOLOGY" and cat2 == "TERMINOLOGY":
                c1 = r1.get("content", {})
                c2 = r2.get("content", {})
                forb1 = _extract_term(c1.get("forbidden_term") or c1.get("term") or c1.get("forbidden") or c1.get("prohibited"))
                pref1 = _extract_term(c1.get("preferred_term") or c1.get("replacement") or c1.get("preferred_alternative") or c1.get("required") or c1.get("prefer"))
                forb2 = _extract_term(c2.get("forbidden_term") or c2.get("term") or c2.get("forbidden") or c2.get("prohibited"))
                pref2 = _extract_term(c2.get("preferred_term") or c2.get("replacement") or c2.get("preferred_alternative") or c2.get("required") or c2.get("prefer"))

                # Direct inverted clash: A forbids X and prefers Y; B forbids Y and prefers X
                if forb1 and pref1 and forb2 and pref2:
                    if forb1 == pref2 and pref1 == forb2:
                        contradictions.append(
                            ContradictionItem(
                                conflict_id=_generate_conflict_id(r1.get("rule_id", "1"), r2.get("rule_id", "2")),
                                conflict_type="TERMINOLOGY",
                                severity="CRITICAL",
                                explanation=(
                                    f"Direct inverted terminology conflict: [{r1.get('rule_code')}] prohibits '{forb1}' in favor of '{pref1}', "
                                    f"while [{r2.get('rule_code')}] prohibits '{forb2}' in favor of '{pref2}'."
                                ),
                                rule_a=_make_excerpt(r1),
                                rule_b=_make_excerpt(r2),
                            )
                        )
                        continue

                # Collision: A forbids X, but B mandates or prefers X
                if forb1 and pref2 and forb1 == pref2:
                    contradictions.append(
                        ContradictionItem(
                            conflict_id=_generate_conflict_id(r1.get("rule_id", "1"), r2.get("rule_id", "2")),
                            conflict_type="TERMINOLOGY",
                            severity="CRITICAL",
                            explanation=(
                                f"Conflicting terminology mandate: [{r1.get('rule_code')}] prohibits '{forb1}', "
                                f"while [{r2.get('rule_code')}] mandates using '{pref2}'."
                            ),
                            rule_a=_make_excerpt(r1),
                            rule_b=_make_excerpt(r2),
                        )
                    )
                    continue

                if forb2 and pref1 and forb2 == pref1:
                    contradictions.append(
                        ContradictionItem(
                            conflict_id=_generate_conflict_id(r1.get("rule_id", "1"), r2.get("rule_id", "2")),
                            conflict_type="TERMINOLOGY",
                            severity="CRITICAL",
                            explanation=(
                                f"Conflicting terminology mandate: [{r2.get('rule_code')}] prohibits '{forb2}', "
                                f"while [{r1.get('rule_code')}] mandates using '{pref1}'."
                            ),
                            rule_a=_make_excerpt(r1),
                            rule_b=_make_excerpt(r2),
                        )
                    )
                    continue

            # 2. Color Contradictions
            if cat1 in ("COLOR", "VISUAL") and cat2 in ("COLOR", "VISUAL"):
                c1 = r1.get("content", {})
                c2 = r2.get("content", {})
                hex1 = c1.get("hex") or c1.get("hex_code")
                hex2 = c2.get("hex") or c2.get("hex_code")

                # If both define brand colors with divergent hex codes (CIEDE2000 Delta E > 10.0)
                if hex1 and hex2:
                    try:
                        rgb1 = hex_to_rgb(hex1)
                        rgb2 = hex_to_rgb(hex2)
                        lab1 = rgb_to_lab(rgb1)
                        lab2 = rgb_to_lab(rgb2)
                        de = ciede2000(lab1, lab2)
                        if de > 10.0:
                            contradictions.append(
                                ContradictionItem(
                                    conflict_id=_generate_conflict_id(r1.get("rule_id", "1"), r2.get("rule_id", "2")),
                                    conflict_type="COLOR",
                                    severity="CRITICAL",
                                    explanation=(
                                        f"Incompatible brand color specification: [{r1.get('rule_code')}] specifies {hex1}, "
                                        f"while [{r2.get('rule_code')}] specifies {hex2} (CIEDE2000 ΔE₀₀ = {de:.1f})."
                                    ),
                                    rule_a=_make_excerpt(r1),
                                    rule_b=_make_excerpt(r2),
                                )
                            )
                            continue
                    except Exception:
                        pass

            # 3. Factual Claim Contradictions
            if cat1 in ("FACT", "FACTUAL", "FACTUAL_CLAIM") and cat2 in ("FACT", "FACTUAL", "FACTUAL_CLAIM"):
                c1 = r1.get("content", {})
                c2 = r2.get("content", {})
                stmt1 = (c1.get("statement") or c1.get("claim_fact") or c1.get("claim") or "").strip().lower()
                stmt2 = (c2.get("statement") or c2.get("claim_fact") or c2.get("claim") or "").strip().lower()

                # Check year / founded in conflict
                year_re = re.compile(r"founded\s+in\s+(\d{4})")
                m1 = year_re.search(stmt1)
                m2 = year_re.search(stmt2)
                if m1 and m2 and m1.group(1) != m2.group(1):
                    contradictions.append(
                        ContradictionItem(
                            conflict_id=_generate_conflict_id(r1.get("rule_id", "1"), r2.get("rule_id", "2")),
                            conflict_type="FACTUAL",
                            severity="CRITICAL",
                            explanation=(
                                f"Direct factual claim contradiction: [{r1.get('rule_code')}] asserts founded in {m1.group(1)}, "
                                f"which contradicts [{r2.get('rule_code')}] asserting founded in {m2.group(1)}."
                            ),
                            rule_a=_make_excerpt(r1),
                            rule_b=_make_excerpt(r2),
                        )
                    )
                    continue

                # Deterministic check for direct contradiction pairs (e.g. 100% vs synthetic, zero vs non-zero)
                antonym_clashes = [
                    ("100% organic", "synthetic"),
                    ("vegan", "bovine"),
                    ("vegan", "animal-derived"),
                    ("zero downtime", "scheduled downtime"),
                    ("cloud-only", "on-premise only"),
                    ("free", "subscription required"),
                ]
                for term_a, term_b in antonym_clashes:
                    if (term_a in stmt1 and term_b in stmt2) or (term_b in stmt1 and term_a in stmt2):
                        contradictions.append(
                            ContradictionItem(
                                conflict_id=_generate_conflict_id(r1.get("rule_id", "1"), r2.get("rule_id", "2")),
                                conflict_type="FACTUAL",
                                severity="CRITICAL",
                                explanation=(
                                    f"Direct factual claim contradiction: [{r1.get('rule_code')}] asserts '{stmt1}', "
                                    f"which contradicts [{r2.get('rule_code')}] asserting '{stmt2}'."
                                ),
                                rule_a=_make_excerpt(r1),
                                rule_b=_make_excerpt(r2),
                            )
                        )
                        break

    return contradictions
