"""Stage 3.2: Guideline Contradiction Scanner Test Suite.

Verifies:
1. Direct inverted terminology conflict detection.
2. Direct color specification clash detection (CIEDE2000).
3. Direct factual claim contradiction detection.
4. Absence of false positives on non-overlapping guidelines.
5. Deterministic conflict ID generation.
"""
import uuid

import pytest

from app.modules.contradictions.scanner import _generate_conflict_id, scan_for_contradictions


def test_deterministic_conflict_id():
    id1 = str(uuid.uuid4())
    id2 = str(uuid.uuid4())
    cid_a = _generate_conflict_id(id1, id2)
    cid_b = _generate_conflict_id(id2, id1)
    assert cid_a == cid_b
    assert len(cid_a) == 16


def test_detect_terminology_inverted_conflict():
    rules = [
        {
            "rule_id": str(uuid.uuid4()),
            "rule_code": "TERM-001",
            "category": "TERMINOLOGY",
            "content": {"forbidden_term": "Acme Cloud System", "preferred_term": "Acme Cloud Platform"},
        },
        {
            "rule_id": str(uuid.uuid4()),
            "rule_code": "TERM-002",
            "category": "TERMINOLOGY",
            "content": {"forbidden_term": "Acme Cloud Platform", "preferred_term": "Acme Cloud System"},
        },
    ]

    conflicts = scan_for_contradictions(rules)
    assert len(conflicts) == 1
    c = conflicts[0]
    assert c.conflict_type == "TERMINOLOGY"
    assert c.severity == "CRITICAL"
    assert "Direct inverted terminology conflict" in c.explanation
    assert c.rule_a.rule_code == "TERM-001"
    assert c.rule_b.rule_code == "TERM-002"


def test_detect_terminology_collision():
    rules = [
        {
            "rule_id": str(uuid.uuid4()),
            "rule_code": "TERM-001",
            "category": "TERMINOLOGY",
            "content": {"forbidden_term": "legacy tool", "preferred_term": "modern platform"},
        },
        {
            "rule_id": str(uuid.uuid4()),
            "rule_code": "TERM-003",
            "category": "TERMINOLOGY",
            "content": {"forbidden_term": "old stack", "preferred_term": "legacy tool"},
        },
    ]

    conflicts = scan_for_contradictions(rules)
    assert len(conflicts) == 1
    c = conflicts[0]
    assert c.conflict_type == "TERMINOLOGY"
    assert c.severity == "CRITICAL"
    assert "Conflicting terminology mandate" in c.explanation


def test_detect_color_clash_conflict():
    rules = [
        {
            "rule_id": str(uuid.uuid4()),
            "rule_code": "COLOR-PRIMARY-BLUE",
            "category": "COLOR",
            "content": {"name": "Primary Brand Color", "hex": "#0055FF"},
        },
        {
            "rule_id": str(uuid.uuid4()),
            "rule_code": "COLOR-PRIMARY-RED",
            "category": "COLOR",
            "content": {"name": "Primary Brand Color", "hex": "#FF1100"},
        },
    ]

    conflicts = scan_for_contradictions(rules)
    assert len(conflicts) == 1
    c = conflicts[0]
    assert c.conflict_type == "COLOR"
    assert c.severity == "CRITICAL"
    assert "Incompatible brand color specification" in c.explanation


def test_detect_factual_contradiction():
    rules = [
        {
            "rule_id": str(uuid.uuid4()),
            "rule_code": "FACT-001",
            "category": "FACT",
            "content": {"statement": "All ingredients are 100% organic certified."},
        },
        {
            "rule_id": str(uuid.uuid4()),
            "rule_code": "FACT-002",
            "category": "FACT",
            "content": {"statement": "Formulated with synthetic stabilizers for shelf life."},
        },
    ]

    conflicts = scan_for_contradictions(rules)
    assert len(conflicts) == 1
    c = conflicts[0]
    assert c.conflict_type == "FACTUAL"
    assert c.severity == "CRITICAL"
    assert "Direct factual claim contradiction" in c.explanation


def test_no_false_positives_on_harmonious_rules():
    rules = [
        {
            "rule_id": str(uuid.uuid4()),
            "rule_code": "TERM-001",
            "category": "TERMINOLOGY",
            "content": {"forbidden_term": "bad term", "preferred_term": "good term"},
        },
        {
            "rule_id": str(uuid.uuid4()),
            "rule_code": "COLOR-001",
            "category": "COLOR",
            "content": {"name": "Primary Brand Blue", "hex": "#0055FF"},
        },
        {
            "rule_id": str(uuid.uuid4()),
            "rule_code": "FACT-001",
            "category": "FACT",
            "content": {"statement": "Acme Cloud delivers enterprise cloud services worldwide."},
        },
    ]

    conflicts = scan_for_contradictions(rules)
    assert len(conflicts) == 0

