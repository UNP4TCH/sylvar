import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import VisualAuditPanel from "./VisualAuditPanel";

describe("VisualAuditPanel", () => {
  it("renders dominant color palette swatches and hex values", () => {
    const visualCheck = {
      check_id: "chk-1",
      engine_type: "VISUAL",
      status: "WARNING",
      execution_time_ms: 8,
      summary_details: {
        dominant_palette: ["#0F172A", "#FFFFFF", "#FF007F"],
        wcag_contrast: {
          contrast_ratio: 17.85,
          compliant_aa: true,
          c1_hex: "#0F172A",
          c2_hex: "#FFFFFF",
        },
      },
    };

    render(
      <VisualAuditPanel
        visualCheck={visualCheck}
        visualFindings={[]}
        imageUrl="data:image/png;base64,sample"
      />
    );

    expect(screen.getByText("Multimodal Visual Brand Compliance")).toBeInTheDocument();
    expect(screen.getAllByText("#0F172A").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("#FFFFFF").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("#FF007F")).toBeInTheDocument();
  });

  it("displays WCAG 2.1 AA compliant contrast badge and ratio", () => {
    const visualCheck = {
      check_id: "chk-2",
      engine_type: "VISUAL",
      status: "PASS",
      execution_time_ms: 12,
      summary_details: {
        dominant_palette: ["#000000", "#FFFFFF"],
        wcag_contrast: {
          contrast_ratio: 21.0,
          compliant_aa: true,
          c1_hex: "#000000",
          c2_hex: "#FFFFFF",
        },
      },
    };

    render(<VisualAuditPanel visualCheck={visualCheck} visualFindings={[]} />);

    expect(screen.getByText("21.00:1")).toBeInTheDocument();
    expect(screen.getByText("AA Compliant (≥ 4.5:1)")).toBeInTheDocument();
  });

  it("displays visual advisory findings with CIEDE2000 Delta E distance", () => {
    const findings = [
      {
        finding_id: "f-1",
        rule_code: "BRAND-COLOR-PRIMARY",
        severity: "ADVISORY",
        message: "Dominant color #FF007F differs from nearest brand color #0F172A (ΔE₀₀ = 49.2).",
        snippet: null,
        evidence: { delta_e: 49.2 },
      },
    ];

    render(<VisualAuditPanel visualFindings={findings} />);

    expect(screen.getByText("BRAND-COLOR-PRIMARY")).toBeInTheDocument();
    expect(screen.getByText("49.2")).toBeInTheDocument();
    expect(screen.getByText(/ADVISORY ONLY/i)).toBeInTheDocument();
  });
});

