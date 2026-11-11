import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import ContradictionsView from "./ContradictionsView";

describe("ContradictionsView", () => {
  it("renders trigger button and initial empty state", () => {
    const mockApi = {
      get: vi.fn(),
      post: vi.fn(),
      patch: vi.fn(),
      delete: vi.fn(),
    };

    render(
      <ContradictionsView
        api={mockApi as any}
        workspaceId="ws-1"
        clientId="cl-1"
        isBrandManager={true}
      />
    );

    expect(screen.getByText("Guideline Contradiction Scanner")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /scan brand guidelines for contradictions/i })).toBeInTheDocument();
  });

  it("triggers contradiction scan and displays detected conflicts", async () => {
    const mockScanResponse = {
      workspace_id: "ws-1",
      client_id: "cl-1",
      rules_scanned_count: 6,
      contradictions_count: 1,
      has_critical_conflicts: true,
      contradictions: [
        {
          conflict_id: "conf-12345",
          conflict_type: "TERMINOLOGY",
          severity: "CRITICAL",
          explanation: "Direct inverted terminology conflict: Rule A mandates 'pro' while Rule B mandates 'basic'.",
          rule_a: {
            rule_id: "r-1",
            rule_code: "RULE-TERM-01",
            category: "TERMINOLOGY",
            statement: "Do not use 'basic' instead use 'pro'.",
            forbidden_term: "basic",
            preferred_term: "pro",
          },
          rule_b: {
            rule_id: "r-2",
            rule_code: "RULE-TERM-02",
            category: "TERMINOLOGY",
            statement: "Do not use 'pro' instead use 'basic'.",
            forbidden_term: "pro",
            preferred_term: "basic",
          },
        },
      ],
    };

    const mockApi = {
      get: vi.fn(),
      post: vi.fn().mockResolvedValue(mockScanResponse),
      patch: vi.fn(),
      delete: vi.fn(),
    };

    render(
      <ContradictionsView
        api={mockApi as any}
        workspaceId="ws-1"
        clientId="cl-1"
        isBrandManager={true}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: /scan brand guidelines for contradictions/i }));

    await waitFor(() => {
      expect(screen.getByText("conf-12345", { exact: false })).toBeInTheDocument();
      expect(screen.getByText("RULE-TERM-01", { exact: false })).toBeInTheDocument();
      expect(screen.getByText("RULE-TERM-02", { exact: false })).toBeInTheDocument();
      expect(screen.getByText(/Direct inverted terminology conflict/i)).toBeInTheDocument();
    });
  });
});

