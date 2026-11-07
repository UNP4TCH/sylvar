"""Tests for Gemini-backed Guideline Extraction Adapter (TASK-017)."""
from unittest.mock import MagicMock, patch

from app.modules.documents.extractor import extract_candidate_rules
from app.modules.documents.gemini_extractor import (
    ExtractedRuleItem,
    ExtractedRulesResponse,
    extract_candidate_rules_with_gemini,
)
from app.modules.documents.parser import ParsedSection


def test_gemini_extractor_parses_rules_correctly():
    sections = [
        ParsedSection(
            section_number=1,
            heading="Brand Voice & Tone",
            content="Never use 'cheap'. Instead use 'accessible luxury'. Hex color #1A2B3C.",
            page_number=1,
        )
    ]

    mock_response = ExtractedRulesResponse(
        candidates=[
            ExtractedRuleItem(
                category="TERMINOLOGY",
                payload={
                    "term": "cheap",
                    "preferred_alternative": "accessible luxury",
                    "severity": "CRITICAL",
                },
                rationale="Brand prohibited term.",
            ),
            ExtractedRuleItem(
                category="COLOR",
                payload={
                    "hex_code": "#1A2B3C",
                    "delta_e_threshold": 5.0,
                    "severity": "ADVISORY",
                },
                rationale="Primary brand palette color.",
            ),
        ]
    )

    with patch("google.genai.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.models.generate_content.return_value = MagicMock(
            text=mock_response.model_dump_json()
        )

        candidates = extract_candidate_rules_with_gemini(
            sections,
            api_key="test-key",
            model="gemini-3.8-flash",
        )

        assert len(candidates) == 2
        assert candidates[0]["category"] == "TERMINOLOGY"
        assert candidates[0]["payload"]["term"] == "cheap"
        assert candidates[1]["category"] == "COLOR"
        assert candidates[1]["payload"]["hex_code"] == "#1A2B3C"


def test_extractor_offline_fallback_when_no_api_key():
    sections = [
        ParsedSection(
            section_number=1,
            heading="Guidelines",
            content="Do not use 'cheap'; instead use 'accessible luxury'. Color: #FF0000.",
            page_number=1,
        )
    ]

    candidates = extract_candidate_rules(sections, api_key=None)

    assert len(candidates) >= 2
    term_cand = next(c for c in candidates if c["category"] == "TERMINOLOGY")
    assert term_cand["payload"]["term"].lower() == "cheap"

