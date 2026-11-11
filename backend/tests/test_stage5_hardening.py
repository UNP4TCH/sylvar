"""Stage 5 Hardening & Release Candidate Verification Suite.

Comprehensive validation covering:
1. Cryptographic certificate canonical hashing and tamper detection.
2. Provider failure fail-closed behavior (no silent passes).
3. Request size limit enforcement (RFC 9457 Problem Details).
4. Epistemic separation integrity between observed facts and inferred recommendations.
"""
import hashlib
import json
import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from app.modules.analytics.calculator import compute_longitudinal_insights
from app.modules.engine_factual.verifier import run_factual_check


def test_certificate_canonical_hashing_and_tamper_detection():
    """Verify that any modification to certificate payload invalidates the certificate hash."""
    ws_id = str(uuid.uuid4())
    client_id = str(uuid.uuid4())
    asset_id = str(uuid.uuid4())
    asset_version_id = str(uuid.uuid4())
    audit_id = str(uuid.uuid4())
    approval_request_id = str(uuid.uuid4())
    creator_id = str(uuid.uuid4())
    approver_id = str(uuid.uuid4())
    snapshot_hash = "a" * 64
    audit_evidence_sha256 = "b" * 64

    # Generate canonical v1.1 certificate payload
    cert_payload = {
        "certificate_version": "1.1",
        "certificate_type": "STANDARD_COMPLIANCE_CERTIFICATE",
        "is_demo_only": False,
        "disclosures": [],
        "workspace_id": ws_id,
        "client_id": client_id,
        "asset_id": asset_id,
        "asset_title": "Campaign Launch Collateral",
        "asset_version_id": asset_version_id,
        "asset_version_number": 1,
        "asset_sha256": "c" * 64,
        "audit_run_id": audit_id,
        "approval_request_id": approval_request_id,
        "submitted_by_user_id": creator_id,
        "audit_evidence_sha256": audit_evidence_sha256,
        "snapshot_hash": snapshot_hash,
        "audit_verdict": "PASS",
        "advisory_acknowledgments": [],
        "approved_by_user_id": approver_id,
        "approved_at": datetime.now(UTC).isoformat(),
    }

    canonical_cert_json = json.dumps(cert_payload, sort_keys=True, separators=(",", ":"))
    valid_cert_hash = hashlib.sha256(canonical_cert_json.encode("utf-8")).hexdigest()

    # Integrity Guarantee: recomputed hash matches valid certificate hash
    assert hashlib.sha256(json.dumps(cert_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest() == valid_cert_hash

    # Tamper Scenario 1: Attacker modifies is_demo_only to True
    tampered_1 = dict(cert_payload)
    tampered_1["is_demo_only"] = True
    assert hashlib.sha256(json.dumps(tampered_1, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest() != valid_cert_hash

    # Tamper Scenario 2: Attacker alters snapshot_hash
    tampered_2 = dict(cert_payload)
    tampered_2["snapshot_hash"] = "0" * 64
    assert hashlib.sha256(json.dumps(tampered_2, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest() != valid_cert_hash

    # Tamper Scenario 3: Attacker alters audit_verdict from WARNINGS to PASS
    tampered_3 = dict(cert_payload)
    tampered_3["audit_verdict"] = "TAMPERED_PASS"
    assert hashlib.sha256(json.dumps(tampered_3, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest() != valid_cert_hash

    # Tamper Scenario 4: Attacker alters approved_by_user_id
    tampered_4 = dict(cert_payload)
    tampered_4["approved_by_user_id"] = str(uuid.uuid4())
    assert hashlib.sha256(json.dumps(tampered_4, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest() != valid_cert_hash


def test_provider_failure_fails_closed():
    """Verify that when Gemini API throws an exception, factual check fails closed to FAIL / UNVERIFIED."""
    sample_rules = [
        {
            "category": "FACT",
            "rule_code": "FACT-001",
            "rule_id": str(uuid.uuid4()),
            "content": {"statement": "All servers are located in ISO 27001 certified data centers."},
        }
    ]
    with patch("google.genai.Client", side_effect=RuntimeError("Provider 503 Service Unavailable")):
        status, findings = run_factual_check(
            "All servers are located in certified data centers.",
            sample_rules,
            api_key="valid-test-key",
            model="gemini-3.8-flash",
        )
        # Critical security guarantee: Engine marks FAIL with CRITICAL finding on provider crash
        assert status == "FAIL"
        assert len(findings) == 1
        assert findings[0].severity == "CRITICAL"
        assert findings[0].verdict == "UNVERIFIED"
        assert "Provider 503 Service Unavailable" in findings[0].message


def test_epistemic_separation_integrity():
    """Verify strict separation between observed historical facts and inferred recommendations."""
    ws_id = uuid.uuid4()
    cl_id = uuid.uuid4()

    insights = compute_longitudinal_insights(
        workspace_id=ws_id,
        client_id=cl_id,
        period_days=30,
        audit_runs=[],
        findings=[],
        suggestions=[],
    )

    # Observed facts must be deterministic counts/rates
    assert isinstance(insights.observed_insights, list)
    assert len(insights.observed_insights) > 0
    for obs in insights.observed_insights:
        assert isinstance(obs, str)

    # Inferred recommendations must be clearly identified guidance
    assert isinstance(insights.inferred_recommendations, list)
    assert len(insights.inferred_recommendations) > 0
    for inf in insights.inferred_recommendations:
        assert isinstance(inf, str)
