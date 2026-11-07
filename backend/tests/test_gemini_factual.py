"""Tests for Gemini-backed Factual Verification and Epistemic Grounding (TASK-023 / TASK-025)."""
from unittest.mock import MagicMock, patch

from app.modules.engine_factual.gemini_verifier import (
    GeminiClaimResult,
    GeminiFactualResponse,
    verify_facts_with_gemini,
)
from app.modules.engine_factual.verifier import run_factual_check


def test_gemini_factual_supported_claim_with_verbatim_citation():
    sample_rules = [
        {
            "category": "FACT",
            "rule_code": "FACT-001",
            "rule_id": "00000000-0000-0000-0000-000000000001",
            "content": {"statement": "All botanical extracts are certified organic by USDA."},
        }
    ]

    mock_response = GeminiFactualResponse(
        findings=[
            GeminiClaimResult(
                claim="Our botanical extracts are certified organic.",
                verdict="SUPPORTED",
                cited_fact="certified organic",
                rationale="Directly supported by reference fact FACT-001.",
                suggested_correction=None,
            )
        ]
    )

    with patch("google.genai.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.models.generate_content.return_value = MagicMock(
            text=mock_response.model_dump_json()
        )

        status, findings = verify_facts_with_gemini(
            "Our botanical extracts are certified organic.",
            sample_rules,
            api_key="test-key",
            model="gemini-3.8-flash",
        )

        assert status == "PASS"
        assert len(findings) == 0  # SUPPORTED claims do not generate violation findings


def test_gemini_factual_contradicted_claim_generates_critical_finding():
    sample_rules = [
        {
            "category": "FACT",
            "rule_code": "FACT-002",
            "rule_id": "00000000-0000-0000-0000-000000000002",
            "content": {"statement": "Our formula is 100% vegan and cruelty-free."},
        }
    ]

    mock_response = GeminiFactualResponse(
        findings=[
            GeminiClaimResult(
                claim="Formulated with bovine collagen peptides.",
                verdict="CONTRADICTED",
                cited_fact="100% vegan",
                rationale="Bovine collagen contradicts the 100% vegan requirement.",
                suggested_correction="Use plant-based collagen alternatives.",
            )
        ]
    )

    with patch("google.genai.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.models.generate_content.return_value = MagicMock(
            text=mock_response.model_dump_json()
        )

        status, findings = verify_facts_with_gemini(
            "Formulated with bovine collagen peptides.",
            sample_rules,
            api_key="test-key",
            model="gemini-3.8-flash",
        )

        assert status == "FAIL"
        assert len(findings) == 1
        assert findings[0].severity == "CRITICAL"
        assert findings[0].verdict == "CONTRADICTED"
        assert findings[0].rule_code == "FACT-002"
        assert findings[0].evidence["citation"] == "100% vegan"


def test_gemini_factual_ungrounded_citation_fails_closed_to_unverified():
    sample_rules = [
        {
            "category": "FACT",
            "rule_code": "FACT-003",
            "rule_id": "00000000-0000-0000-0000-000000000003",
            "content": {"statement": "Packaging is 100% post-consumer recycled plastic."},
        }
    ]

    # Model hallucinates a citation that does NOT exist anywhere in reference facts
    mock_response = GeminiFactualResponse(
        findings=[
            GeminiClaimResult(
                claim="Certified carbon neutral facility.",
                verdict="SUPPORTED",
                cited_fact="100% zero carbon emissions certified",  # Hallucinated string!
                rationale="Allegedly stated in facts.",
            )
        ]
    )

    with patch("google.genai.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.models.generate_content.return_value = MagicMock(
            text=mock_response.model_dump_json()
        )

        status, findings = verify_facts_with_gemini(
            "Certified carbon neutral facility.",
            sample_rules,
            api_key="test-key",
            model="gemini-3.8-flash",
        )

        # Must fail closed to UNVERIFIED / WARNING because citation was ungrounded
        assert status == "WARNING"
        assert len(findings) == 1
        assert findings[0].verdict == "UNVERIFIED"
        assert findings[0].severity == "MAJOR"


def test_run_factual_check_offline_fallback():
    sample_rules = [
        {
            "category": "FACT",
            "rule_code": "FACT-001",
            "content": {"statement": "All botanical extracts are certified organic."},
        }
    ]

    # No api_key provided -> uses deterministic NLP heuristics
    status, findings = run_factual_check(
        "Our serum uses synthetic chemicals.",
        sample_rules,
        api_key=None,
    )

    assert status == "FAIL"
    assert len(findings) == 1
    assert findings[0].verdict == "CONTRADICTED"
    assert findings[0].severity == "CRITICAL"



def test_gemini_empty_findings_does_not_pass_unchecked_claims():
    sample_rules = [
        {"category": "FACT", "rule_code": "FACT-001", "content": {"statement": "Made in India."}}
    ]
    empty_response = GeminiFactualResponse(findings=[])
    with patch("google.genai.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.models.generate_content.return_value = MagicMock(text=empty_response.model_dump_json())
        status, findings = verify_facts_with_gemini(
            "Our products are made in India.", sample_rules, api_key="test-key"
        )
    assert status == "FAIL"
    assert len(findings) == 1
    assert findings[0].verdict == "UNVERIFIED"
    assert findings[0].severity == "CRITICAL"
    assert findings[0].evidence["reason"] == "MODEL_CLAIM_OMISSION"


def test_offline_clean_heuristic_is_not_compliance_pass():
    status, _findings = run_factual_check(
        "Our product is a premium solution.",
        [{"category": "FACT", "content": {"statement": "Made in India."}}],
        api_key=None,
    )
    assert status == "FAIL"
