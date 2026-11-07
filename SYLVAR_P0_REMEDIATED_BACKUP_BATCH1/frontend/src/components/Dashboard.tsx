import { useEffect, useState } from "react";
import { getSupabase } from "../lib/supabase";
import { createAuthedClient } from "../lib/authedApi";

interface Workspace {
  workspace_id: string;
  name: string;
  slug: string;
}

interface ClientBrand {
  client_id: string;
  name: string;
  code: string;
}

interface ExtractedCandidate {
  candidate_id: string;
  category: string;
  payload: Record<string, unknown>;
  review_status: string;
}

interface Finding {
  finding_id: string;
  rule_code: string | null;
  severity: string;
  message: string;
  snippet: string | null;
  evidence: Record<string, unknown>;
  suggestions: Array<{
    suggestion_id: string;
    original_text: string;
    suggested_text: string;
    rationale: string;
  }>;
}

interface AuditCheck {
  check_id: string;
  engine_type: string;
  status: string;
  execution_time_ms: number;
}

interface AuditRun {
  audit_run_id: string;
  asset_id: string;
  asset_version_id: string;
  snapshot_id: string;
  status: string;
  overall_verdict: string;
  checks: AuditCheck[];
  findings: Finding[];
}

interface ReviewItem {
  review_id: string;
  status: string;
  decision_notes: string | null;
  certificate?: {
    certificate_id: string;
    certificate_hash: string;
    snapshot_hash: string;
    certificate_payload: Record<string, unknown>;
    issued_at: string;
  } | null;
}

interface UserProfile {
  user_id: string;
  email: string;
  workspaces: Array<{
    workspace_id: string;
    workspace_name: string;
    role: string;
  }>;
  client_assignments: Array<{
    workspace_id: string;
    client_id: string;
    client_name: string;
    client_role: string;
  }>;
}

export default function Dashboard({ apiBaseUrl }: { apiBaseUrl: string }) {
  const [userProfile, setUserProfile] = useState<UserProfile | null>(null);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [selectedWs, setSelectedWs] = useState<string>("");
  const [clients, setClients] = useState<ClientBrand[]>([]);
  const [selectedClient, setSelectedClient] = useState<string>("");

  // Memory & Ingestion state
  const [guidelineText, setGuidelineText] = useState(
    "Never use 'cheap'; instead use 'accessible luxury'.\nBrand Color: #1A2B3C.\nFactual: All botanical extracts are certified organic."
  );
  const [candidates, setCandidates] = useState<ExtractedCandidate[]>([]);
  const [activeSnapshotHash, setActiveSnapshotHash] = useState<string | null>(null);

  // Content & Audit state
  const [contentTitle, setContentTitle] = useState("Launch Campaign Copy");
  const [contentText, setContentText] = useState(
    "Our cheap serum is formulated with a synthetic base for glowing skin."
  );
  const [currentAssetId, setCurrentAssetId] = useState<string | null>(null);
  const [currentVersionId, setCurrentVersionId] = useState<string | null>(null);
  const [currentVersionNumber, setCurrentVersionNumber] = useState<number>(1);
  const [latestAudit, setLatestAudit] = useState<AuditRun | null>(null);

  // Review & Compliance state
  const [reviews, setReviews] = useState<ReviewItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  // Member management state
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("BRAND_MANAGER");
  const [showMemberModal, setShowMemberModal] = useState(false);

  const api = createAuthedClient(getSupabase, apiBaseUrl);

  // Load User Profile and Workspaces on mount
  useEffect(() => {
    void loadProfile();
    void loadWorkspaces();
  }, []);

  async function loadProfile() {
    try {
      const data = await api.get<UserProfile>("/api/v1/users/me");
      setUserProfile(data);
    } catch {
      // Profile fetch optional during initial state
    }
  }

  async function loadWorkspaces() {
    try {
      const data = await api.get<Workspace[]>("/api/v1/workspaces");
      setWorkspaces(data);
      if (data.length > 0 && !selectedWs) {
        setSelectedWs(data[0].workspace_id);
      }
    } catch (err) {
      console.warn("Could not load workspaces:", err);
    }
  }

  // Load Clients when Workspace changes
  useEffect(() => {
    if (!selectedWs) return;
    void loadClients(selectedWs);
  }, [selectedWs]);

  async function loadClients(wId: string) {
    try {
      const data = await api.get<ClientBrand[]>(`/api/v1/workspaces/${wId}/clients`);
      setClients(data);
      if (data.length > 0) {
        setSelectedClient(data[0].client_id);
      } else {
        setSelectedClient("");
      }
    } catch (err) {
      setClients([]);
      console.warn(`Could not load clients for workspace ${wId}:`, err);
    }
  }

  // Check active memory for client
  useEffect(() => {
    if (!selectedWs || !selectedClient) return;
    void checkActiveMemory();
    void loadCandidates();
    void loadReviews();
  }, [selectedWs, selectedClient]);

  async function checkActiveMemory() {
    try {
      const res = await api.get<{
        active: boolean;
        snapshot?: { snapshot_hash: string } | null;
      }>(`/api/v1/workspaces/${selectedWs}/clients/${selectedClient}/memory/active`);
      setActiveSnapshotHash(res.snapshot?.snapshot_hash ?? null);
    } catch {
      setActiveSnapshotHash(null);
    }
  }

  async function loadCandidates() {
    try {
      const res = await api.get<ExtractedCandidate[]>(
        `/api/v1/workspaces/${selectedWs}/clients/${selectedClient}/candidates`
      );
      setCandidates(res);
    } catch {
      setCandidates([]);
    }
  }

  async function loadReviews() {
    try {
      const res = await api.get<ReviewItem[]>(
        `/api/v1/workspaces/${selectedWs}/clients/${selectedClient}/reviews`
      );
      setReviews(res);
    } catch {
      setReviews([]);
    }
  }

  async function handleCreateWorkspace() {
    setLoading(true);
    try {
      const slug = `agency-${Date.now().toString(36)}`;
      const res = await api.post<Workspace>("/api/v1/workspaces", {
        name: "Omni Brand Agency",
        slug,
      });
      setWorkspaces((prev) => [...prev, res]);
      setSelectedWs(res.workspace_id);
      await loadProfile();
      setMessage("Workspace created.");
    } catch (err) {
      setMessage(`Failed to create workspace: ${String(err)}`);
    } finally {
      setLoading(false);
    }
  }

  async function handleCreateClient() {
    if (!selectedWs) return;
    setLoading(true);
    try {
      const code = `CLIENT_${Date.now().toString(36).toUpperCase()}`;
      const res = await api.post<ClientBrand>(`/api/v1/workspaces/${selectedWs}/clients`, {
        name: "Verve Botanicals",
        code,
      });

      // ADR-003: Assign creator as BRAND_MANAGER so they have access to client data
      try {
        const me = await api.get<{ user_id: string }>("/api/v1/users/me");
        await api.post(`/api/v1/workspaces/${selectedWs}/clients/${res.client_id}/members`, {
          user_id: me.user_id,
          client_role: "BRAND_MANAGER",
        });
      } catch {
        // If already assigned, ignore
      }

      setClients((prev) => [...prev, res]);
      setSelectedClient(res.client_id);
      await loadProfile();
      setMessage("Client brand created and Brand Manager role assigned.");
    } catch (err) {
      setMessage(`Failed to create client: ${String(err)}`);
    } finally {
      setLoading(false);
    }
  }

  async function handleInviteMember() {
    if (!selectedWs || !inviteEmail.trim()) return;
    setLoading(true);
    try {
      await api.post(`/api/v1/workspaces/${selectedWs}/members`, {
        email: inviteEmail.trim(),
        role: inviteRole,
        full_name: inviteEmail.split("@")[0],
      });
      setMessage(`Member invited to workspace with role ${inviteRole}.`);
      setInviteEmail("");
      setShowMemberModal(false);
    } catch (err) {
      setMessage(`Failed to invite member: ${String(err)}`);
    } finally {
      setLoading(false);
    }
  }

  async function handleUploadGuidelines() {
    if (!selectedWs || !selectedClient) return;
    setLoading(true);
    try {
      const formData = new FormData();
      formData.append("title", "Core Brand Guidelines");
      formData.append(
        "file",
        new Blob([guidelineText], { type: "text/plain" }),
        "guidelines.txt"
      );

      await api.post(
        `/api/v1/workspaces/${selectedWs}/clients/${selectedClient}/documents`,
        formData
      );
      await loadCandidates();
      setMessage("Guidelines uploaded and rules extracted.");
    } catch (err) {
      setMessage(`Guideline upload failed: ${String(err)}`);
    } finally {
      setLoading(false);
    }
  }

  async function handleFileUpload(e: React.ChangeEvent<HTMLInputElement>) {
    if (!selectedWs || !selectedClient || !e.target.files || e.target.files.length === 0) return;
    const file = e.target.files[0];
    setLoading(true);
    try {
      const formData = new FormData();
      formData.append("title", file.name);
      formData.append("file", file, file.name);

      await api.post(
        `/api/v1/workspaces/${selectedWs}/clients/${selectedClient}/documents`,
        formData
      );
      await loadCandidates();
      setMessage(`File '${file.name}' uploaded and processed successfully.`);
    } catch (err) {
      setMessage(`File upload failed: ${String(err)}`);
    } finally {
      setLoading(false);
      e.target.value = "";
    }
  }

  async function handleApproveAndActivate() {
    if (!selectedWs || !selectedClient || candidates.length === 0) return;
    setLoading(true);
    try {
      // 1. Approve candidates
      const candIds = candidates.map((c) => c.candidate_id);
      await api.post(
        `/api/v1/workspaces/${selectedWs}/clients/${selectedClient}/knowledge/approve`,
        { candidate_ids: candIds }
      );

      // 2. Activate memory
      const actRes = await api.post<{ snapshot_hash: string }>(
        `/api/v1/workspaces/${selectedWs}/clients/${selectedClient}/memory/activate`,
        { version_tag: "v1.0.0", change_summary: "Approved baseline rules" }
      );
      setActiveSnapshotHash(actRes.snapshot_hash);
      setMessage(`Memory activated! Snapshot SHA-256: ${actRes.snapshot_hash.slice(0, 16)}…`);
    } catch (err) {
      setMessage(`Memory activation failed: ${String(err)}`);
    } finally {
      setLoading(false);
    }
  }

  async function handleRunAudit() {
    if (!selectedWs || !selectedClient) return;
    setLoading(true);
    try {
      // 1. Create or use current asset
      let aId = currentAssetId;
      let vId = currentVersionId;
      if (!aId) {
        const assetRes = await api.post<{
          asset_id: string;
          latest_version: { version_id: string; version_number: number };
        }>(`/api/v1/workspaces/${selectedWs}/clients/${selectedClient}/assets`, {
          title: contentTitle,
          content_type: "TEXT",
          text_content: contentText,
        });
        aId = assetRes.asset_id;
        vId = assetRes.latest_version.version_id;
        setCurrentAssetId(aId);
        setCurrentVersionId(vId);
        setCurrentVersionNumber(assetRes.latest_version.version_number);
      }

      // 2. Trigger audit
      const auditRes = await api.post<AuditRun>(
        `/api/v1/workspaces/${selectedWs}/clients/${selectedClient}/assets/${aId}/versions/${vId}/audit`
      );
      setLatestAudit(auditRes);
      setMessage(`Audit completed with verdict: ${auditRes.overall_verdict}`);
    } catch (err) {
      setMessage(`Audit execution failed: ${String(err)}`);
    } finally {
      setLoading(false);
    }
  }

  async function handleApplyRemediation(suggId: string) {
    if (!selectedWs || !selectedClient || !latestAudit) return;
    setLoading(true);
    try {
      const res = await api.post<{
        version_id: string;
        version_number: number;
        text_content: string;
      }>(
        `/api/v1/workspaces/${selectedWs}/clients/${selectedClient}/audits/${latestAudit.audit_run_id}/remediate`,
        { suggestion_ids: [suggId] }
      );
      setCurrentVersionId(res.version_id);
      setCurrentVersionNumber(res.version_number);
      setContentText(res.text_content);

      // Re-audit version
      const reAudit = await api.post<AuditRun>(
        `/api/v1/workspaces/${selectedWs}/clients/${selectedClient}/assets/${latestAudit.asset_id}/versions/${res.version_id}/audit`
      );
      setLatestAudit(reAudit);
      setMessage(
        `Applied surgical fix! Version forked to v${res.version_number}. Re-audit verdict: ${reAudit.overall_verdict}`
      );
    } catch (err) {
      setMessage(`Remediation failed: ${String(err)}`);
    } finally {
      setLoading(false);
    }
  }

  async function handleSubmitReview() {
    if (!selectedWs || !selectedClient || !currentAssetId || !currentVersionId || !latestAudit)
      return;
    setLoading(true);
    try {
      await api.post(`/api/v1/workspaces/${selectedWs}/clients/${selectedClient}/reviews`, {
        asset_id: currentAssetId,
        asset_version_id: currentVersionId,
        audit_run_id: latestAudit.audit_run_id,
        submission_notes: "Clean copy submitted for Brand Manager sign-off.",
      });
      await loadReviews();
      setMessage("Content submitted to Brand Manager Review Queue.");
    } catch (err) {
      setMessage(`Submission failed: ${String(err)}`);
    } finally {
      setLoading(false);
    }
  }

  async function handleApproveReview(revId: string) {
    if (!selectedWs || !selectedClient) return;
    setLoading(true);
    try {
      await api.post(
        `/api/v1/workspaces/${selectedWs}/clients/${selectedClient}/reviews/${revId}/decision`,
        {
          decision: "APPROVED",
          decision_notes: "Verified against living brand memory snapshot.",
          advisory_acknowledgments: latestAudit.findings
            .filter((finding) => ["MAJOR", "MINOR", "ADVISORY"].includes(finding.severity))
            .map((finding) => finding.finding_id),
        }
      );
      await loadReviews();
      setMessage("Review APPROVED and Compliance Certificate issued!");
    } catch (err) {
      setMessage(`Approval failed: ${String(err)}`);
    } finally {
      setLoading(false);
    }
  }

  async function handleRejectReview(revId: string) {
    if (!selectedWs || !selectedClient) return;
    setLoading(true);
    try {
      await api.post(
        `/api/v1/workspaces/${selectedWs}/clients/${selectedClient}/reviews/${revId}/decision`,
        {
          decision: "REJECTED",
          decision_notes: "Rejected due to brand guideline non-compliance.",
          advisory_acknowledgments: [],
        }
      );
      await loadReviews();
      setMessage("Review status updated to REJECTED.");
    } catch (err) {
      setMessage(`Action failed: ${String(err)}`);
    } finally {
      setLoading(false);
    }
  }

  async function handleRequestChangesReview(revId: string) {
    if (!selectedWs || !selectedClient) return;
    setLoading(true);
    try {
      await api.post(
        `/api/v1/workspaces/${selectedWs}/clients/${selectedClient}/reviews/${revId}/decision`,
        {
          decision: "CHANGES_REQUESTED",
          decision_notes: "Please refine claim substantiation and resubmit.",
          advisory_acknowledgments: [],
        }
      );
      await loadReviews();
      setMessage("Changes requested from content creator.");
    } catch (err) {
      setMessage(`Action failed: ${String(err)}`);
    } finally {
      setLoading(false);
    }
  }

  function downloadCertificate(cert: NonNullable<ReviewItem["certificate"]>) {
    const blob = new Blob([JSON.stringify(cert.certificate_payload, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `sylvar-certificate-${cert.certificate_hash.slice(0, 8)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="w-full max-w-5xl mx-auto p-4 space-y-6">
      {message && (
        <div
          role="status"
          className="p-3 bg-blue-50 border border-blue-200 text-blue-900 rounded-lg text-sm flex justify-between items-center"
        >
          <span>{message}</span>
          <button
            onClick={() => setMessage(null)}
            className="text-xs font-semibold uppercase px-2 py-1 hover:bg-blue-100 rounded"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* TOP BAR: Workspace & Client Scoping */}
      <div className="bg-white border rounded-xl p-4 shadow-sm flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <div>
            <label className="block text-xs font-medium text-gray-500 uppercase tracking-wider">
              Workspace
            </label>
            <div className="flex items-center gap-2 mt-1">
              <select
                className="border rounded px-2 py-1 text-sm bg-white"
                value={selectedWs}
                onChange={(e) => setSelectedWs(e.target.value)}
              >
                {workspaces.map((w) => (
                  <option key={w.workspace_id} value={w.workspace_id}>
                    {w.name}
                  </option>
                ))}
              </select>
              <button
                onClick={() => void handleCreateWorkspace()}
                disabled={loading}
                className="text-xs bg-gray-100 hover:bg-gray-200 border rounded px-2 py-1"
              >
                + New
              </button>
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-500 uppercase tracking-wider">
              Client Brand
            </label>
            <div className="flex items-center gap-2 mt-1">
              <select
                className="border rounded px-2 py-1 text-sm bg-white"
                value={selectedClient}
                onChange={(e) => setSelectedClient(e.target.value)}
              >
                {clients.map((c) => (
                  <option key={c.client_id} value={c.client_id}>
                    {c.name} ({c.code})
                  </option>
                ))}
              </select>
              <button
                onClick={() => void handleCreateClient()}
                disabled={loading || !selectedWs}
                className="text-xs bg-gray-100 hover:bg-gray-200 border rounded px-2 py-1"
              >
                + New
              </button>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => setShowMemberModal(true)}
            disabled={!selectedWs}
            className="text-xs text-indigo-700 bg-indigo-50 border border-indigo-200 px-2.5 py-1 rounded hover:bg-indigo-100 font-medium"
          >
            Team & Scoping
          </button>
          <div>
            <span className="text-xs text-gray-500">Active Memory:</span>
            {activeSnapshotHash ? (
              <span className="ml-2 font-mono text-xs bg-emerald-100 text-emerald-800 px-2 py-1 rounded">
                SHA-256: {activeSnapshotHash.slice(0, 10)}…
              </span>
            ) : (
              <span className="ml-2 text-xs bg-amber-100 text-amber-800 px-2 py-1 rounded">
                No Active Memory
              </span>
            )}
          </div>
        </div>
      </div>

      {/* TEAM & SCOPING MODAL */}
      {showMemberModal && (
        <div className="bg-indigo-50 border border-indigo-200 rounded-xl p-4 text-xs space-y-3">
          <div className="flex justify-between items-center font-semibold text-indigo-950">
            <span>Workspace Membership & Client Brand Scoping (ADR-003)</span>
            <button onClick={() => setShowMemberModal(false)} className="text-gray-500 hover:text-black">
              ✕ Close
            </button>
          </div>
          {userProfile && (
            <p className="text-gray-700">
              Authenticated user: <span className="font-mono font-medium">{userProfile.email}</span>
            </p>
          )}
          <div className="flex gap-2 items-center">
            <input
              type="email"
              placeholder="member@agency.com"
              value={inviteEmail}
              onChange={(e) => setInviteEmail(e.target.value)}
              className="border rounded px-2 py-1 bg-white text-xs w-64"
            />
            <select
              value={inviteRole}
              onChange={(e) => setInviteRole(e.target.value)}
              className="border rounded px-2 py-1 bg-white text-xs"
            >
              <option value="BRAND_MANAGER">Brand Manager</option>
              <option value="CONTENT_CREATOR">Content Creator</option>
              <option value="WORKSPACE_ADMIN">Workspace Admin</option>
            </select>
            <button
              onClick={() => void handleInviteMember()}
              disabled={loading || !inviteEmail.trim()}
              className="bg-indigo-600 text-white px-3 py-1 rounded hover:bg-indigo-700 disabled:opacity-50"
            >
              Invite Member
            </button>
          </div>
        </div>
      )}

      {/* STEP 1: Living Brand Memory Ingestion (Brand Manager) */}
      <div className="bg-white border rounded-xl p-5 shadow-sm space-y-4">
        <div className="flex justify-between items-center border-b pb-2">
          <h2 className="text-lg font-semibold text-gray-900">
            1. Living Brand Memory & Guideline Ingestion
          </h2>
          <span className="text-xs bg-purple-100 text-purple-800 px-2 py-0.5 rounded font-medium">
            Brand Manager Role
          </span>
        </div>
        <p className="text-sm text-gray-600">
          Upload or paste brand guideline documents (PDF, DOCX, Markdown, TXT). SYLVAR extracts
          structured rules across Terminology, Color, and Facts.
        </p>

        <div className="flex items-center gap-3">
          <label className="text-xs font-medium text-gray-700">Upload Guideline File:</label>
          <input
            type="file"
            accept=".txt,.md,.docx,.pdf"
            onChange={(e) => void handleFileUpload(e)}
            disabled={loading || !selectedClient}
            className="text-xs file:mr-2 file:py-1 file:px-2.5 file:rounded file:border-0 file:text-xs file:bg-gray-100 hover:file:bg-gray-200"
          />
        </div>

        <textarea
          rows={3}
          value={guidelineText}
          onChange={(e) => setGuidelineText(e.target.value)}
          className="w-full border rounded-lg p-2.5 font-mono text-xs bg-gray-50 focus:bg-white"
          placeholder="Paste brand guideline text here..."
        />
        <div className="flex gap-2">
          <button
            onClick={() => void handleUploadGuidelines()}
            disabled={loading || !selectedClient}
            className="text-xs bg-blue-600 text-white font-medium px-3 py-1.5 rounded hover:bg-blue-700 disabled:opacity-50"
          >
            Upload & Extract Rules
          </button>
          <button
            onClick={() => void handleApproveAndActivate()}
            disabled={loading || candidates.length === 0}
            className="text-xs bg-emerald-600 text-white font-medium px-3 py-1.5 rounded hover:bg-emerald-700 disabled:opacity-50"
          >
            Approve & Activate Memory Release ({candidates.length} Staged Candidates)
          </button>
        </div>
      </div>

      {/* STEP 2: Content Creation & Pre-Publication Audit (Content Creator) */}
      <div className="bg-white border rounded-xl p-5 shadow-sm space-y-4">
        <div className="flex justify-between items-center border-b pb-2">
          <h2 className="text-lg font-semibold text-gray-900">
            2. Content Governance Studio & Pre-Publication CI/CD
          </h2>
          <span className="text-xs bg-blue-100 text-blue-800 px-2 py-0.5 rounded font-medium">
            Content Creator Role (Version {currentVersionNumber})
          </span>
        </div>
        <div className="space-y-2">
          <input
            type="text"
            value={contentTitle}
            onChange={(e) => setContentTitle(e.target.value)}
            className="w-full border rounded px-3 py-1.5 text-sm font-medium"
            placeholder="Asset Title"
          />
          <textarea
            rows={3}
            value={contentText}
            onChange={(e) => setContentText(e.target.value)}
            className="w-full border rounded-lg p-2.5 text-sm"
          />
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => void handleRunAudit()}
            disabled={loading || !activeSnapshotHash}
            className="text-xs bg-indigo-600 text-white font-medium px-4 py-2 rounded hover:bg-indigo-700 disabled:opacity-50"
          >
            Run Pre-Publication Audit
          </button>
          <button
            onClick={() =>
              setContentText(
                "Our cheap serum is formulated with a synthetic base for glowing skin."
              )
            }
            className="text-xs border px-3 py-1.5 rounded hover:bg-gray-50 text-gray-700"
          >
            Load Non-Compliant Draft
          </button>
          <button
            onClick={() =>
              setContentText(
                "Our accessible luxury serum features certified organic botanical extracts."
              )
            }
            className="text-xs border px-3 py-1.5 rounded hover:bg-gray-50 text-gray-700"
          >
            Load Compliant Draft
          </button>
        </div>

        {/* Live Diagnostic Scorecard */}
        {latestAudit && (
          <div className="mt-4 border rounded-lg p-4 bg-gray-50 space-y-3">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-sm text-gray-800">Diagnostic Scorecard:</span>
              <span
                className={`px-3 py-1 rounded text-xs font-bold tracking-wider ${
                  latestAudit.overall_verdict === "BLOCKED"
                    ? "bg-red-600 text-white"
                    : latestAudit.overall_verdict === "WARNINGS"
                    ? "bg-amber-500 text-white"
                    : "bg-emerald-600 text-white"
                }`}
              >
                {latestAudit.overall_verdict}
              </span>
            </div>

            {/* Engine Checks Summary */}
            <div className="grid grid-cols-3 gap-2">
              {latestAudit.checks.map((c) => (
                <div key={c.check_id} className="bg-white border rounded p-2 text-xs">
                  <div className="text-gray-500 uppercase">{c.engine_type}</div>
                  <div className="font-bold mt-0.5">{c.status}</div>
                </div>
              ))}
            </div>

            {/* Findings & Surgical Suggestions */}
            {latestAudit.findings.length > 0 ? (
              <div className="space-y-2 mt-2">
                <span className="text-xs font-semibold text-gray-700">Findings:</span>
                {latestAudit.findings.map((f) => (
                  <div
                    key={f.finding_id}
                    className="bg-white border border-l-4 border-l-red-500 rounded p-3 text-xs space-y-1.5"
                  >
                    <div className="flex justify-between items-center">
                      <span className="font-mono text-gray-500">{f.rule_code}</span>
                      <span className="bg-red-100 text-red-800 px-1.5 py-0.5 rounded font-bold">
                        {f.severity}
                      </span>
                    </div>
                    <p className="text-gray-800">{f.message}</p>
                    {f.snippet && (
                      <div className="p-1.5 bg-gray-100 font-mono text-gray-700 rounded text-2xs">
                        Snippet: &ldquo;{f.snippet}&rdquo;
                      </div>
                    )}
                    {f.suggestions.map((s) => (
                      <div
                        key={s.suggestion_id}
                        className="bg-emerald-50 border border-emerald-200 rounded p-2 flex justify-between items-center"
                      >
                        <div>
                          <span className="text-emerald-900 font-semibold">Suggested Fix: </span>
                          <span className="text-emerald-700">&ldquo;{s.suggested_text}&rdquo;</span>
                          <p className="text-gray-500 text-2xs">{s.rationale}</p>
                        </div>
                        <button
                          onClick={() => void handleApplyRemediation(s.suggestion_id)}
                          className="bg-emerald-600 text-white px-2 py-1 rounded text-2xs font-semibold hover:bg-emerald-700"
                        >
                          Apply Surgical Fix
                        </button>
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-emerald-700 font-medium">
                ✓ 0 compliance violations detected. Content matches approved brand memory.
              </p>
            )}

            {/* Submit to review button */}
            <div className="pt-2 border-t flex justify-end">
              <button
                onClick={() => void handleSubmitReview()}
                disabled={latestAudit.overall_verdict === "BLOCKED" || loading}
                className="text-xs bg-blue-600 text-white font-medium px-4 py-2 rounded hover:bg-blue-700 disabled:opacity-40"
              >
                Submit Clean Version for Brand Manager Approval
              </button>
            </div>
          </div>
        )}
      </div>

      {/* STEP 3: Brand Manager Review Queue & Verifiable Certificate (Phase 5) */}
      <div className="bg-white border rounded-xl p-5 shadow-sm space-y-4">
        <div className="flex justify-between items-center border-b pb-2">
          <h2 className="text-lg font-semibold text-gray-900">
            3. Brand Manager Review Queue & Compliance Certificates
          </h2>
          <span className="text-xs bg-purple-100 text-purple-800 px-2 py-0.5 rounded font-medium">
            Brand Manager Role
          </span>
        </div>

        {reviews.length > 0 ? (
          <div className="space-y-3">
            {reviews.map((r) => (
              <div key={r.review_id} className="border rounded-lg p-4 bg-gray-50 space-y-2">
                <div className="flex justify-between items-center">
                  <span className="font-semibold text-sm">Review Request #{r.review_id.slice(0, 8)}</span>
                  <span
                    className={`text-xs px-2 py-0.5 rounded font-bold ${
                      r.status === "APPROVED"
                        ? "bg-emerald-100 text-emerald-800"
                        : r.status === "REJECTED"
                        ? "bg-red-100 text-red-800"
                        : r.status === "CHANGES_REQUESTED"
                        ? "bg-blue-100 text-blue-800"
                        : "bg-amber-100 text-amber-800"
                    }`}
                  >
                    {r.status}
                  </span>
                </div>
                {r.decision_notes && (
                  <p className="text-xs text-gray-600">Notes: {r.decision_notes}</p>
                )}

                {r.status === "PENDING" && (
                  <div className="flex gap-2 pt-2">
                    <button
                      onClick={() => void handleApproveReview(r.review_id)}
                      disabled={loading}
                      className="text-xs bg-emerald-600 text-white font-medium px-3 py-1.5 rounded hover:bg-emerald-700"
                    >
                      Approve & Issue Certificate
                    </button>
                    <button
                      onClick={() => void handleRequestChangesReview(r.review_id)}
                      disabled={loading}
                      className="text-xs bg-blue-600 text-white font-medium px-3 py-1.5 rounded hover:bg-blue-700"
                    >
                      Request Changes
                    </button>
                    <button
                      onClick={() => void handleRejectReview(r.review_id)}
                      disabled={loading}
                      className="text-xs bg-red-600 text-white font-medium px-3 py-1.5 rounded hover:bg-red-700"
                    >
                      Reject
                    </button>
                  </div>
                )}

                {r.certificate && (
                  <div className="mt-3 bg-white border border-emerald-300 rounded p-3 text-xs space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-emerald-700 font-bold">
                        ✓ VERIFIED COMPLIANCE CERTIFICATE
                      </span>
                      <button
                        onClick={() => downloadCertificate(r.certificate!)}
                        className="text-2xs bg-emerald-50 text-emerald-800 border border-emerald-300 px-2 py-1 rounded hover:bg-emerald-100 font-medium"
                      >
                        Export Certificate JSON
                      </button>
                    </div>
                    <div className="font-mono text-gray-600 text-2xs">
                      Certificate SHA-256: {r.certificate.certificate_hash}
                    </div>
                    <div className="font-mono text-gray-600 text-2xs">
                      Snapshot SHA-256: {r.certificate.snapshot_hash}
                    </div>
                    <div className="text-gray-500 text-2xs">
                      Issued: {new Date(r.certificate.issued_at).toLocaleString()}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        ) : (
          <p className="text-xs text-gray-500 italic">No approval requests in the review queue.</p>
        )}
      </div>
    </div>
  );
}
