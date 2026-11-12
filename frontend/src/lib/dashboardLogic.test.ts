import {
  classifyCandidate,
  getActivationBlockReason,
  getUploadBlockReason,
  nextVersionTag,
  summarizeCandidates,
  type UploadContext,
} from "./dashboardLogic";

test("only PENDING_REVIEW is classified as pending; MODIFIED_APPROVED is not re-submitted", () => {
  expect(classifyCandidate("PENDING_REVIEW")).toBe("pending");
  expect(classifyCandidate("APPROVED")).toBe("approved");
  expect(classifyCandidate("MODIFIED_APPROVED")).toBe("approved");
  expect(classifyCandidate("REJECTED")).toBe("rejected");
  expect(classifyCandidate("SOMETHING_NEW")).toBe("unknown");
  expect(classifyCandidate("")).toBe("unknown");
});

test("summary counts every bucket and totals them", () => {
  const s = summarizeCandidates([
    { review_status: "PENDING_REVIEW" },
    { review_status: "PENDING_REVIEW" },
    { review_status: "APPROVED" },
    { review_status: "MODIFIED_APPROVED" },
    { review_status: "REJECTED" },
    { review_status: "WEIRD" },
  ]);
  expect(s).toEqual({ pending: 2, approved: 2, rejected: 1, unknown: 1, total: 6 });
});

test("version tag: first release is v1.1.0, then increments from the real current number", () => {
  expect(nextVersionTag(null)).toBe("v1.1.0");
  expect(nextVersionTag(1)).toBe("v1.2.0");
  expect(nextVersionTag(7)).toBe("v1.8.0");
});

const base: UploadContext = {
  selectedWs: "w1", selectedClient: "c1", workspacesStatus: "loaded", clientsStatus: "loaded",
  workspacesError: null, clientsError: null,
};

test("upload allowed only with workspace and client", () => {
  expect(getUploadBlockReason(base)).toBeNull();
});

test("upload blocked for non-brand-manager", () => {
  const blocked = getUploadBlockReason({ ...base, isBrandManager: false });
  expect(blocked).toContain("restricted to Brand Managers");
});

test("no workspace: says so, and surfaces the real load error when the list failed", () => {
  expect(getUploadBlockReason({ ...base, selectedWs: "", selectedClient: "", workspacesStatus: "loaded" })).toContain("no workspace is selected");
  const failed = getUploadBlockReason({
    ...base, selectedWs: "", selectedClient: "", workspacesStatus: "error",
    workspacesError: "Could not load workspaces: Forbidden (HTTP 403)",
  });
  expect(failed).toContain("failed to load");
  expect(failed).toContain("HTTP 403");
});

test("workspace but no client: distinguishes loading, failed and genuinely empty", () => {
  const ctx = { ...base, selectedClient: "" };
  expect(getUploadBlockReason({ ...ctx, clientsStatus: "loading" })).toContain("still loading");
  expect(getUploadBlockReason({ ...ctx, clientsStatus: "error", clientsError: "boom (HTTP 500)" })).toContain("HTTP 500");
  expect(getUploadBlockReason({ ...ctx, clientsStatus: "loaded" })).toContain("no client brand visible to you");
});

const sum = { pending: 1, approved: 0, rejected: 0, unknown: 0, total: 1 };

test("activation is blocked when the current memory version is unknown, and the real error is shown", () => {
  const r = getActivationBlockReason({ memoryStatus: "error", memoryError: "Could not read ... (HTTP 500)", summary: sum });
  expect(r).toContain("blocked");
  expect(r).toContain("HTTP 500");
});

test("activation blocked for non-brand-manager", () => {
  const r = getActivationBlockReason({ memoryStatus: "loaded", memoryError: null, summary: sum, isBrandManager: false });
  expect(r).toContain("restricted to Brand Managers");
});

test("activation blocked while loading, with no client, or with nothing to activate; allowed otherwise", () => {
  expect(getActivationBlockReason({ memoryStatus: "loading", memoryError: null, summary: sum })).not.toBeNull();
  expect(getActivationBlockReason({ memoryStatus: "idle", memoryError: null, summary: sum })).not.toBeNull();
  expect(getActivationBlockReason({ memoryStatus: "loaded", memoryError: null, summary: { ...sum, pending: 0 } })).toContain("Nothing to activate");
  expect(getActivationBlockReason({ memoryStatus: "loaded", memoryError: null, summary: sum })).toBeNull();
  expect(getActivationBlockReason({ memoryStatus: "loaded", memoryError: null, summary: { ...sum, pending: 0, approved: 2 } })).toBeNull();
});
