/** Pure decision logic for the Dashboard, kept out of the component so it is unit-testable. */

export type LoadStatus = "idle" | "loading" | "loaded" | "error";

// ---- candidates -------------------------------------------------------------------------------
export type CandidateBucket = "pending" | "approved" | "rejected" | "unknown";

/**
 * Maps a backend review_status to a UI bucket. Only PENDING_REVIEW is ever sent to the approve endpoint.
 * MODIFIED_APPROVED is treated as already approved (its name says so). Anything unrecognised is shown
 * with its raw status and is never submitted, so unknown lifecycle states cannot be pushed through.
 */
export function classifyCandidate(status: string): CandidateBucket {
  if (status === "PENDING_REVIEW") return "pending";
  if (status === "APPROVED" || status === "MODIFIED_APPROVED") return "approved";
  if (status.startsWith("REJECT")) return "rejected";
  return "unknown";
}

export interface CandidateSummary {
  pending: number;
  approved: number;
  rejected: number;
  unknown: number;
  total: number;
}

export function summarizeCandidates(cands: Array<{ review_status: string }>): CandidateSummary {
  const s: CandidateSummary = { pending: 0, approved: 0, rejected: 0, unknown: 0, total: cands.length };
  for (const c of cands) s[classifyCandidate(c.review_status)] += 1;
  return s;
}

// ---- memory version ---------------------------------------------------------------------------
/** Same tag scheme as before (v1.<n>.0). Only call with a version read successfully from the API. */
export function nextVersionTag(currentVersionNumber: number | null): string {
  return `v1.${(currentVersionNumber ?? 0) + 1}.0`;
}

// ---- upload gating ----------------------------------------------------------------------------
export interface UploadContext {
  selectedWs: string;
  selectedClient: string;
  workspacesStatus: LoadStatus;
  clientsStatus: LoadStatus;
  workspacesError: string | null;
  clientsError: string | null;
  isBrandManager?: boolean;
}

/** null = upload allowed. Otherwise the exact reason it is not. */
export function getUploadBlockReason(c: UploadContext): string | null {
  if (c.isBrandManager === false) {
    return "Guideline ingestion and candidate rule extraction are restricted to Brand Managers. Your current client assignment is CONTENT_CREATOR.";
  }
  if (!c.selectedWs) {
    if (c.workspacesStatus === "loading") return "Workspaces are still loading.";
    if (c.workspacesStatus === "error")
      return `Upload unavailable: the workspace list failed to load. ${c.workspacesError ?? ""}`.trim();
    return "Upload unavailable: no workspace is selected. Create or select a workspace first.";
  }
  if (!c.selectedClient) {
    if (c.clientsStatus === "loading") return "Client brands are still loading.";
    if (c.clientsStatus === "error")
      return `Upload unavailable: this workspace's client brands failed to load. ${c.clientsError ?? ""}`.trim();
    if (c.clientsStatus === "loaded")
      return "Upload unavailable: this workspace has no client brand visible to you. Guidelines are stored against a client brand, so create or select one first.";
    return "Upload unavailable: no client brand is selected.";
  }
  return null;
}

// ---- activation gating ------------------------------------------------------------------------
export interface ActivationContext {
  memoryStatus: LoadStatus;
  memoryError: string | null;
  summary: CandidateSummary;
  isBrandManager?: boolean;
}

export function getActivationBlockReason(c: ActivationContext): string | null {
  if (c.isBrandManager === false) {
    return "Living brand memory activation is restricted to Brand Managers. Your current client assignment is CONTENT_CREATOR.";
  }
  if (c.memoryStatus === "loading") return "Checking the current active memory version…";
  if (c.memoryStatus === "error")
    return `Activation blocked: the current memory version could not be read, so a new version tag cannot be chosen safely. ${c.memoryError ?? ""}`.trim();
  if (c.memoryStatus === "idle") return "Activation unavailable: no client brand is selected.";
  if (c.summary.pending === 0 && c.summary.approved === 0)
    return "Nothing to activate: there are no pending or approved candidate rules.";
  return null;
}
