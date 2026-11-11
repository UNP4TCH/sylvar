import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import AnalyticsView from "./AnalyticsView";

describe("AnalyticsView", () => {
  it("loads and renders longitudinal compliance metrics and epistemic separation", async () => {
    const mockAnalyticsResponse = {
      workspace_id: "ws-1",
      client_id: "cl-1",
      period_days: 30,
      total_audits: 12,
      pass_rate_pct: 75.0,
      block_rate_pct: 16.7,
      warnings_rate_pct: 8.3,
      remediation_adoption: {
        total_suggestions_generated: 10,
        applied_suggestions_count: 8,
        adoption_rate_pct: 80.0,
      },
      top_recurring_violations: [
        {
          rule_code: "TERM-FORBIDDEN-01",
          category: "TERMINOLOGY",
          violation_count: 5,
          affected_assets_count: 3,
          severity: "CRITICAL",
          sample_snippet: "prohibited cloud term",
        },
      ],
      temporal_trends: [
        {
          date: "2026-11-10",
          total_audits: 4,
          passed_count: 3,
          blocked_count: 1,
          warnings_count: 0,
        },
      ],
      observed_insights: [
        "Conducted 12 audits in the last 30 days.",
        "Pass rate is 75.0% across all collateral.",
      ],
      inferred_recommendations: [
        "Upstream briefing recommended for terminology guidelines.",
      ],
    };

    const mockApi = {
      get: vi.fn().mockResolvedValue(mockAnalyticsResponse),
      post: vi.fn(),
      patch: vi.fn(),
      delete: vi.fn(),
    };

    render(
      <AnalyticsView
        api={mockApi as any}
        workspaceId="ws-1"
        clientId="cl-1"
      />
    );

    await waitFor(() => {
      expect(screen.getByText("Longitudinal Brand Compliance Insights")).toBeInTheDocument();
      expect(screen.getByText("75.0%")).toBeInTheDocument();
      expect(screen.getByText("80.0%")).toBeInTheDocument();
      expect(screen.getByText("Observed Historical Metrics")).toBeInTheDocument();
      expect(screen.getByText("Inferred Governance Recommendations")).toBeInTheDocument();
      expect(screen.getByText("TERM-FORBIDDEN-01")).toBeInTheDocument();
      expect(screen.getByText("Conducted 12 audits in the last 30 days.")).toBeInTheDocument();
      expect(screen.getByText("Upstream briefing recommended for terminology guidelines.")).toBeInTheDocument();
    });
  });
});

