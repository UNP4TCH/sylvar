"""Visual Compliance Engine (TASK-024).

Adheres to ADR-008 (Advisory Visual Math):
- Linear-light alpha compositing over neutral white background for RGBA assets.
- CIELAB conversion with D65 illuminant.
- Pure Python CIEDE2000 color difference formula (Delta E 00).
- Off-brand dominant colors (Delta E 00 > 5.0) are strictly ADVISORY, never blocking.
"""
import io
import math
from dataclasses import dataclass
from typing import Any

from PIL import Image


@dataclass
class VisualFinding:
    rule_id: str | None
    rule_code: str
    severity: str  # ADVISORY (ADR-008)
    message: str
    dominant_hex: str
    closest_brand_hex: str
    delta_e: float
    evidence: dict[str, Any]


def hex_to_rgb(hex_code: str) -> tuple[int, int, int]:
    """Parse hex code (#RRGGBB) to (R, G, B)."""
    hex_clean = hex_code.lstrip("#")
    if len(hex_clean) == 3:
        hex_clean = "".join(c * 2 for c in hex_clean)
    if len(hex_clean) != 6:
        return (0, 0, 0)
    return (int(hex_clean[0:2], 16), int(hex_clean[2:4], 16), int(hex_clean[4:6], 16))


def rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02x}{g:02x}{b:02x}".upper()


def rgb_to_lab(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
    """Convert sRGB (0-255) to CIELAB with D65 standard illuminant."""
    # 1. Linearize sRGB
    r_lin = rgb[0] / 255.0
    g_lin = rgb[1] / 255.0
    b_lin = rgb[2] / 255.0

    def linearize(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r_lin = linearize(r_lin)
    g_lin = linearize(g_lin)
    b_lin = linearize(b_lin)

    # 2. Linear sRGB to XYZ (D65)
    x = r_lin * 0.4124564 + g_lin * 0.3575761 + b_lin * 0.1804375
    y = r_lin * 0.2126729 + g_lin * 0.7151522 + b_lin * 0.0721750
    z = r_lin * 0.0193339 + g_lin * 0.1191920 + b_lin * 0.9503041

    # D65 reference white points
    xn, yn, zn = 0.95047, 1.00000, 1.08883
    xr = x / xn
    yr = y / yn
    zr = z / zn

    delta = 6.0 / 29.0

    def f(t: float) -> float:
        return t ** (1.0 / 3.0) if t > delta**3 else (t / (3.0 * delta**2)) + (4.0 / 29.0)

    fx = f(xr)
    fy = f(yr)
    fz = f(zr)

    l_star = max(0.0, 116.0 * fy - 16.0)
    a_star = 500.0 * (fx - fy)
    b_star = 200.0 * (fy - fz)

    return (l_star, a_star, b_star)


def ciede2000(lab1: tuple[float, float, float], lab2: tuple[float, float, float]) -> float:
    """Compute CIEDE2000 color difference between two CIELAB colors."""
    l1, a1, b1 = lab1
    l2, a2, b2 = lab2

    c1 = math.hypot(a1, b1)
    c2 = math.hypot(a2, b2)
    c_bar = (c1 + c2) / 2.0

    g = 0.5 * (1.0 - math.sqrt((c_bar**7) / (c_bar**7 + 25.0**7))) if c_bar > 0 else 0.0

    a1_prime = (1.0 + g) * a1
    a2_prime = (1.0 + g) * a2

    c1_prime = math.hypot(a1_prime, b1)
    c2_prime = math.hypot(a2_prime, b2)

    def compute_h_prime(a_p: float, b_p: float) -> float:
        if a_p == 0.0 and b_p == 0.0:
            return 0.0
        deg = math.degrees(math.atan2(b_p, a_p))
        return deg if deg >= 0.0 else deg + 360.0

    h1_prime = compute_h_prime(a1_prime, b1)
    h2_prime = compute_h_prime(a2_prime, b2)

    delta_l_prime = l2 - l1
    delta_c_prime = c2_prime - c1_prime

    if c1_prime * c2_prime == 0.0:
        delta_h_prime = 0.0
    elif abs(h2_prime - h1_prime) <= 180.0:
        delta_h_prime = h2_prime - h1_prime
    elif h2_prime - h1_prime > 180.0:
        delta_h_prime = (h2_prime - h1_prime) - 360.0
    else:
        delta_h_prime = (h2_prime - h1_prime) + 360.0

    delta_h_capital = 2.0 * math.sqrt(c1_prime * c2_prime) * math.sin(math.radians(delta_h_prime / 2.0))

    l_bar_prime = (l1 + l2) / 2.0
    c_bar_prime = (c1_prime + c2_prime) / 2.0

    if c1_prime * c2_prime == 0.0:
        h_bar_prime = h1_prime + h2_prime
    elif abs(h1_prime - h2_prime) <= 180.0:
        h_bar_prime = (h1_prime + h2_prime) / 2.0
    elif h1_prime + h2_prime < 360.0:
        h_bar_prime = (h1_prime + h2_prime + 360.0) / 2.0
    else:
        h_bar_prime = (h1_prime + h2_prime - 360.0) / 2.0

    t = (
        1.0
        - 0.17 * math.cos(math.radians(h_bar_prime - 30.0))
        + 0.24 * math.cos(math.radians(2.0 * h_bar_prime))
        + 0.32 * math.cos(math.radians(3.0 * h_bar_prime + 6.0))
        - 0.20 * math.cos(math.radians(4.0 * h_bar_prime - 63.0))
    )

    delta_theta = 30.0 * math.exp(-(((h_bar_prime - 275.0) / 25.0) ** 2))
    r_c = 2.0 * math.sqrt((c_bar_prime**7) / (c_bar_prime**7 + 25.0**7)) if c_bar_prime > 0 else 0.0

    s_l = 1.0 + ((0.015 * ((l_bar_prime - 50.0) ** 2)) / math.sqrt(20.0 + ((l_bar_prime - 50.0) ** 2)))
    s_c = 1.0 + 0.045 * c_bar_prime
    s_h = 1.0 + 0.015 * c_bar_prime * t
    r_t = -math.sin(math.radians(2.0 * delta_theta)) * r_c

    term_l = delta_l_prime / s_l
    term_c = delta_c_prime / s_c
    term_h = delta_h_capital / s_h

    delta_e = math.sqrt(term_l**2 + term_c**2 + term_h**2 + r_t * term_c * term_h)
    return round(delta_e, 2)


def extract_dominant_colors(image_bytes: bytes, max_colors: int = 5) -> list[tuple[int, int, int]]:
    """Extract dominant RGB colors from image, ignoring transparent pixels (M-04)."""
    raw_img = Image.open(io.BytesIO(image_bytes))
    if raw_img.mode in ("RGBA", "LA") or (raw_img.mode == "P" and "transparency" in raw_img.info):
        rgba = raw_img.convert("RGBA")
        # Filter transparent pixels (alpha < 32) to prevent matte canvas from dominating the palette (M-04)
        raw_pixels = list(rgba.getdata())
        opaque_pixels = [(r, g, b) for r, g, b, a in raw_pixels if a >= 32]
        if opaque_pixels:
            # Downsample for efficient quantization
            step = max(1, len(opaque_pixels) // 5000)
            sampled = opaque_pixels[::step]
            w = min(len(sampled), 100)
            h = max(1, len(sampled) // w)
            sample_img = Image.new("RGB", (w, h))
            sample_img.putdata(sampled[: w * h])
            quantized = sample_img.quantize(colors=max_colors)
            palette = quantized.getpalette() or []
            colors = quantized.getcolors(10000) or []
            colors.sort(key=lambda x: x[0], reverse=True)
            dominant: list[tuple[int, int, int]] = []
            for _count, idx in colors[:max_colors]:
                if isinstance(idx, int) and (idx * 3 + 2) < len(palette):
                    r = palette[idx * 3]
                    g = palette[idx * 3 + 1]
                    b = palette[idx * 3 + 2]
                    dominant.append((r, g, b))
            return dominant

        # Fallback if image is completely transparent
        background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        composite = Image.alpha_composite(background, rgba)
        rgb_img = composite.convert("RGB")
    else:
        rgb_img = raw_img.convert("RGB")

    resized = rgb_img.resize((100, 100), Image.Resampling.BOX)
    quantized = resized.quantize(colors=max_colors)
    palette = quantized.getpalette() or []
    colors = quantized.getcolors(10000) or []
    colors.sort(key=lambda x: x[0], reverse=True)

    dominant = []
    for _count, idx in colors[:max_colors]:
        if isinstance(idx, int) and (idx * 3 + 2) < len(palette):
            r = palette[idx * 3]
            g = palette[idx * 3 + 1]
            b = palette[idx * 3 + 2]
            dominant.append((r, g, b))

    return dominant


def run_visual_check(
    image_bytes: bytes, rules: list[dict[str, Any]]
) -> tuple[str, list[VisualFinding]]:
    """Execute visual color compliance check against approved brand color palette.

    Returns:
        (check_status: "PASS" | "WARNING", findings: list[VisualFinding])
    """
    color_rules = [r for r in rules if r.get("category") == "COLOR"]
    if not color_rules:
        return "PASS", []

    brand_colors = []
    for r in color_rules:
        hex_val = r.get("content", {}).get("hex") or r.get("content", {}).get("hex_code")
        if hex_val:
            brand_colors.append(
                {
                    "rule_id": r.get("rule_id"),
                    "rule_code": r.get("rule_code", "RULE-COLOR"),
                    "hex": hex_val,
                    "rgb": hex_to_rgb(hex_val),
                    "lab": rgb_to_lab(hex_to_rgb(hex_val)),
                }
            )

    if not brand_colors:
        return "PASS", []

    dominant_rgbs = extract_dominant_colors(image_bytes)
    findings: list[VisualFinding] = []

    for dom_rgb in dominant_rgbs:
        dom_lab = rgb_to_lab(dom_rgb)
        dom_hex = rgb_to_hex(*dom_rgb)

        # Find closest brand color
        closest = None
        min_de = float("inf")

        for b_col in brand_colors:
            de = ciede2000(dom_lab, b_col["lab"])
            if de < min_de:
                min_de = de
                closest = b_col

        # ADR-008: Delta E > 5.0 is advisory
        if min_de > 5.0 and closest:
            findings.append(
                VisualFinding(
                    rule_id=closest["rule_id"],
                    rule_code=closest["rule_code"],
                    severity="ADVISORY",  # Strictly advisory per ADR-008
                    message=f"Dominant color {dom_hex} differs from nearest brand color {closest['hex']} (ΔE₀₀ = {min_de}).",
                    dominant_hex=dom_hex,
                    closest_brand_hex=closest["hex"],
                    delta_e=min_de,
                    evidence={
                        "dominant_hex": dom_hex,
                        "closest_brand_hex": closest["hex"],
                        "delta_e": min_de,
                        "advisory_threshold": 5.0,
                    },
                )
            )

    status = "WARNING" if findings else "PASS"
    return status, findings
