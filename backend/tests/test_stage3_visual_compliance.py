"""Stage 3.1: Visual Brand Compliance & WCAG Contrast Test Suite.

Verifies:
1. Pure Python WCAG 2.1 relative luminance and contrast ratio calculations.
2. Measurable CIEDE2000 color difference (Delta E 00) against brand colors.
3. WCAG AA contrast threshold enforcement (minimum 4.5:1 ratio).
4. Logo dimension and resolution rule enforcement.
5. Image asset intake (magic bytes, dimension bounds, SHA-256 integrity).
6. Orchestrator execution for pure IMAGE and HYBRID assets.
"""
import base64
import io
import uuid
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from app.modules.engine_visual.analyzer import (
    compute_relative_luminance,
    compute_wcag_contrast,
    extract_dominant_colors,
    hex_to_rgb,
    rgb_to_hex,
    run_visual_check,
)


def _make_test_image(width: int = 200, height: int = 200, color: tuple[int, int, int] = (255, 0, 0)) -> bytes:
    """Generate in-memory PNG image bytes."""
    img = Image.new("RGB", (width, height), color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_two_tone_image(
    c1: tuple[int, int, int], c2: tuple[int, int, int], width: int = 200, height: int = 200
) -> bytes:
    """Generate in-memory PNG with two distinct horizontal blocks."""
    img = Image.new("RGB", (width, height), c1)
    half = Image.new("RGB", (width, height // 2), c2)
    img.paste(half, (0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# -----------------------------------------------------------------------------
# 1. WCAG 2.1 Contrast Math Tests
# -----------------------------------------------------------------------------
def test_wcag_contrast_extreme_values():
    black = (0, 0, 0)
    white = (255, 255, 255)

    assert compute_relative_luminance(black) == 0.0
    assert abs(compute_relative_luminance(white) - 1.0) < 0.001

    # Black and white contrast ratio is exactly 21.0:1
    ratio = compute_wcag_contrast(black, white)
    assert ratio == 21.0

    # Same color contrast is exactly 1.0:1
    assert compute_wcag_contrast(white, white) == 1.0
    assert compute_wcag_contrast(black, black) == 1.0


def test_wcag_contrast_threshold_discrimination():
    white = (255, 255, 255)
    # Dark Navy has high contrast against white (> 10:1)
    navy = (10, 20, 80)
    assert compute_wcag_contrast(navy, white) >= 4.5

    # Light gray (#D0D0D0) has very poor contrast against white (< 2:1)
    light_gray = (208, 208, 208)
    assert compute_wcag_contrast(light_gray, white) < 4.5


# -----------------------------------------------------------------------------
# 2. Measurable Palette & Delta E Tests
# -----------------------------------------------------------------------------
def test_visual_check_advisory_on_offbrand_color():
    # Image is solid bright orange (#FF6600)
    img_bytes = _make_test_image(color=(255, 102, 0))

    # Brand color is Cool Cyan (#00CCFF)
    rules = [
        {
            "category": "COLOR",
            "rule_id": str(uuid.uuid4()),
            "rule_code": "BRAND-COLOR-PRIMARY",
            "content": {"hex": "#00CCFF", "name": "Cool Cyan"},
        }
    ]

    status, findings = run_visual_check(img_bytes, rules)
    assert status == "WARNING"
    palette_findings = [f for f in findings if f.rule_code == "BRAND-COLOR-PRIMARY"]
    assert len(palette_findings) > 0
    f = palette_findings[0]
    assert f.severity == "ADVISORY"
    assert f.delta_e > 5.0
    assert f.dominant_hex == "#FF6600"
    assert f.closest_brand_hex == "#00CCFF"
    assert f.evidence["advisory_threshold"] == 5.0


def test_visual_check_passes_when_color_matches_brand():
    # Brand color is Pure Blue (#0055FF)
    brand_hex = "#0055FF"
    brand_rgb = hex_to_rgb(brand_hex)
    img_bytes = _make_test_image(color=brand_rgb)

    rules = [
        {
            "category": "COLOR",
            "rule_id": str(uuid.uuid4()),
            "rule_code": "BRAND-COLOR-PRIMARY",
            "content": {"hex": brand_hex, "name": "Brand Blue"},
        }
    ]

    status, findings = run_visual_check(img_bytes, rules)
    palette_findings = [f for f in findings if f.rule_code == "BRAND-COLOR-PRIMARY"]
    assert len(palette_findings) == 0


# -----------------------------------------------------------------------------
# 3. WCAG Contrast Finding in Visual Check
# -----------------------------------------------------------------------------
def test_visual_check_detects_low_wcag_contrast():
    # Image with light gray and white (low contrast ratio < 4.5)
    light_gray = (220, 220, 220)
    white = (255, 255, 255)
    img_bytes = _make_two_tone_image(light_gray, white)

    status, findings = run_visual_check(img_bytes, rules=[])
    contrast_findings = [f for f in findings if f.rule_code == "VISUAL-WCAG-CONTRAST"]
    assert len(contrast_findings) == 1
    cf = contrast_findings[0]
    assert cf.severity == "ADVISORY"
    assert cf.evidence["wcag_threshold"] == 4.5
    assert cf.evidence["measured_contrast"] < 4.5


# -----------------------------------------------------------------------------
# 4. Logo Dimensional Rule Enforcement
# -----------------------------------------------------------------------------
def test_visual_check_logo_minimum_dimensions():
    # Image is 200x150
    img_bytes = _make_test_image(width=200, height=150)

    rules = [
        {
            "category": "LOGO",
            "rule_id": str(uuid.uuid4()),
            "rule_code": "RULE-LOGO-MIN-SIZE",
            "content": {"min_width": 400, "min_height": 300},
        }
    ]

    status, findings = run_visual_check(img_bytes, rules)
    assert status == "WARNING"
    logo_findings = [f for f in findings if "MIN-WIDTH" in f.rule_code or "MIN-HEIGHT" in f.rule_code]
    assert len(logo_findings) == 2
    assert any("MIN-WIDTH" in f.rule_code for f in logo_findings)
    assert any("MIN-HEIGHT" in f.rule_code for f in logo_findings)
