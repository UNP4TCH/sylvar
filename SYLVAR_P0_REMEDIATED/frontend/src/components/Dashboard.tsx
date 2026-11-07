import { useEffect, useRef, useState } from "react";
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
  workspace_id?: string;
  client_id?: string;
  asset_id?: string;
  asset_version_id?: string;
  audit_run_id?: string;
  status: string;
  decision_notes: string | null;
  submitted_by_user_id?: string;
  decided_by_user_id?: string | null;
  decided_at?: string | null;
  created_at?: string;
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
  const [selectedWs, setSelectedWs] = useState<string>(() => localStorage.getItem("sylvar_selected_workspace") || "");
  const [showCreateWorkspaceModal, setShowCreateWorkspaceModal] = useState(false);
  const [newWorkspaceName, setNewWorkspaceName] = useState("");
  const [showRenameWorkspaceModal, setShowRenameWorkspaceModal] = useState(false);
  const [renameWorkspaceName, setRenameWorkspaceName] = useState("");
  const [clients, setClients] = useState<ClientBrand[]>([]);
  const [selectedClient, setSelectedClient] = useState<string>("");
  const [showCreateClientModal, setShowCreateClientModal] = useState(false);
  const [newClientName, setNewClientName] = useState("Verve Botanicals");
  const [showRenameClientModal, setShowRenameClientModal] = useState(false);
  const [renameClientName, setRenameClientName] = useState("");

  // Memory & Ingestion state
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [guidelineText, setGuidelineText] = useState(
    "Never use 'cheap'; instead use 'accessible luxury'.\nBrand Color: #1A2B3C.\nFactual: All botanical extracts are certified organic."
  );
  const [candidates, setCandidates] = useState<ExtractedCandidate[]>([]);
  const [activeSnapshotHash, setActiveSnapshotHash] = useState<string | null>(null);
  const [activeVersionNumber, setActiveVersionNumber] = useState<number | null>(null);
  const [activeVersionTag, setActiveVersionTag] = useState<string | null>(null);
  const [isExtracting, setIsExtracting] = useState(false);

  // Content & Audit state
  const [contentTitle, setContentTitle] = useState("Launch Campaign Copy");
  const [contentText, setContentText] = useState(
    "Our cheap serum is formulated with a synthetic base for glowing skin."
  );
  const [currentAssetId, setCurrentAssetId] = useState<string | null>(null);
  const [currentVersionId, setCurrentVersionId] = useState<string | null>(null);
  const [currentVersionNumber, setCurrentVersionNumber] = useState<number>(1);
  const [latestAudit, setLatestAudit] = useState<AuditRun | null>(null);
  const [lastAuditedText, setLastAuditedText] = useState<string | null>(null);

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

  async function loadWorkspaces(preferredWsId?: string) {
    try {
      const data = await api.get<Workspace[]>("/api/v1/workspaces");
      setWorkspaces(data);
      const targetId = preferredWsId || selectedWs || localStorage.getItem("sylvar_selected_workspace");
      const matched = data.find((w) => w.workspace_id === targetId);
      if (matched) {
        setSelectedWs(matched.workspace_id);
      } else if (data.length > 0) {
        setSelectedWs(data[0].workspace_id);
        localStorage.setItem("sylvar_selected_workspace", data[0].workspace_id);
      } else {
        setSelectedWs("");
      }
    } catch (err) {
      console.warn("Could not load workspaces:", err);
    }
  }

  function handleWorkspaceChange(wsId: string) {
    setSelectedWs(wsId);
    localStorage.setItem("sylvar_selected_workspace", wsId);
  }

  // Load Clients when Workspace changes
  useEffect(() => {
    if (!selectedWs) return;
    void loadClients(selectedWs);
  }, [selectedWs]);

  async function loadClients(wId: string, preferredClientId?: string) {
    try {
      const data = await api.get<ClientBrand[]>(`/api/v1/workspaces/${wId}/clients`);
      setClients(data);
      if (preferredClientId && data.some((c) => c.client_id === preferredClientId)) {
        setSelectedClient(preferredClientId);
      } else if (selectedClient && data.some((c) => c.client_id === selectedClient)) {
        // Keep current selected client if it belongs to this workspace
      } else if (data.length > 0) {
        setSelectedClient(data[0].client_id);
      } else {
        setSelectedClient("");
      }
    } catch (err) {
      setClients([]);
      setSelectedClient("");
      console.warn(`Could not load clients for workspace ${wId}:`, err);
    }
  }

  // Check active memory for client and reset draft/audit states to avoid stale references
  useEffect(() => {
    // Reset draft and audit states when workspace or client changes (Task 2)
    setCurrentAssetId(null);
    setCurrentVersionId(null);
    setCurrentVersionNumber(1);
    setLatestAudit(null);
    setLastAuditedText(null);

    if (!selectedWs || !selectedClient) return;
    void checkActiveMemory();
    void loadCandidates();
    void loadReviews();
  }, [selectedWs, selectedClient]);

  async function checkActiveMemory() {
    try {
      const res = await api.get<{
        active: boolean;
        version?: { version_number: number; version_tag: string } | null;
        snapshot?: { snapshot_hash: string } | null;
      }>(`/api/v1/workspaces/${selectedWs}/clients/${selectedClient}/memory/active`);
      setActiveSnapshotHash(res.snapshot?.snapshot_hash ?? null);
      setActiveVersionNumber(res.version?.version_number ?? null);
      setActiveVersionTag(res.version?.version_tag ?? null);
    } catch {
      setActiveSnapshotHash(null);
      setActiveVersionNumber(null);
      setActiveVersionTag(null);
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

  async function handleCreateWorkspaceSubmit(e?: React.FormEvent) {
    if (e) e.preventDefault();
    const name = newWorkspaceName.trim();
    if (!name) return;
    setLoading(true);
    try {
      const baseSlug = name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "agency";
      const slug = `${baseSlug.slice(0, 30)}-${Date.now().toString(36)}`;
      const res = await api.post<Workspace>("/api/v1/workspaces", {
        name,
        slug,
      });
      setWorkspaces((prev) => [...prev, res]);
      setSelectedWs(res.workspace_id);
      localStorage.setItem("sylvar_selected_workspace", res.workspace_id);
      setShowCreateWorkspaceModal(false);
      setNewWorkspaceName("");
      await loadProfile();
      setMessage(`Workspace '${res.name}' created successfully.`);
    } catch (err) {
      setMessage(`Failed to create workspace: ${String(err)}`);
    } finally {
      setLoading(false);
    }
  }

  async function handleRenameWorkspaceSubmit(e?: React.FormEvent) {
    if (e) e.preventDefault();
    if (!selectedWs) return;
    const name = renameWorkspaceName.trim();
    if (!name) return;
    setLoading(true);
    try {
      const res = await api.patch<Workspace>(`/api/v1/workspaces/${selectedWs}`, {
        name,
      });
      setWorkspaces((prev) =>
        prev.map((w) => (w.workspace_id === selectedWs ? { ...w, name: res.name } : w))
      );
      setShowRenameWorkspaceModal(false);
      setRenameWorkspaceName("");
      await loadProfile();
      setMessage(`Workspace renamed to '${res.name}'.`);
    } catch (err) {
      setMessage(`Failed to rename workspace: ${String(err)}`);
    } finally {
      setLoading(false);
    }
  }

  async function handleCreateClient() {
    if (!selectedWs) return;
    const brandName = newClientName.trim() || "Verve Botanicals";
    setLoading(true);
    try {
      const code = `CLIENT_${Date.now().toString(36).toUpperCase()}`;
      const res = await api.post<ClientBrand>(`/api/v1/workspaces/${selectedWs}/clients`, {
        name: brandName,
        code,
      });

      await loadClients(selectedWs, res.client_id);
      setShowCreateClientModal(false);
      setNewClientName("Verve Botanicals");
      await loadProfile();
      setMessage(`Client brand '${brandName}' (${code}) created and Brand Manager role assigned.`);
    } catch (err) {
      setMessage(`Failed to create client: ${String(err)}`);
    } finally {
      setLoading(false);
    }
  }

  async function handleRenameClientSubmit() {
    if (!selectedWs || !selectedClient || !renameClientName.trim()) return;
    const trimmed = renameClientName.trim();
    if (trimmed.length < 2) {
      setMessage("Client brand name must be at least 2 characters.");
      return;
    }
    const isDuplicate = clients.some(
      (c) => c.client_id !== selectedClient && c.name.toLowerCase() === trimmed.toLowerCase()
    );
    if (isDuplicate) {
      setMessage(`A client brand named '${trimmed}' already exists in this workspace.`);
      return;
    }

    setLoading(true);
    try {
      const res = await api.patch<{ client_id: string; name: string; code: string }>(
        `/api/v1/workspaces/${selectedWs}/clients/${selectedClient}`,
        { name: trimmed }
      );
      setClients((prev) =>
        prev.map((c) => (c.client_id === selectedClient ? { ...c, name: res.name } : c))
      );
      setShowRenameClientModal(false);
      await loadProfile();
      setMessage(`Client brand renamed to '${res.name}'.`);
    } catch (err: any) {
      const detail = err?.problem?.detail || err?.message || String(err);
      setMessage(`Failed to rename client brand: ${detail}`);
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

  function handleFileSelected(e: React.ChangeEvent<HTMLInputElement>) {
    if (!e.target.files || e.target.files.length === 0) return;
    const file = e.target.files[0];

    // File validation (Task 4 / Bug 3)
    const ext = file.name.split(".").pop()?.toLowerCase();
    const validExts = ["txt", "md", "docx", "pdf"];
    if (!ext || !validExts.includes(ext)) {
      setMessage(`Unsupported file format '.${ext}'. Allowed formats: .txt, .md, .docx, .pdf`);
      if (fileInputRef.current) fileInputRef.current.value = "";
      setSelectedFile(null);
      return;
    }
    if (file.size === 0) {
      setMessage("Selected file is empty (0 bytes). Please choose a valid document.");
      if (fileInputRef.current) fileInputRef.current.value = "";
      setSelectedFile(null);
      return;
    }
    if (file.size > 25 * 1024 * 1024) {
      setMessage("File exceeds maximum upload size limit of 25 MB.");
      if (fileInputRef.current) fileInputRef.current.value = "";
      setSelectedFile(null);
      return;
    }

    setSelectedFile(file);
    setMessage(`Selected file '${file.name}' (${(file.size / 1024).toFixed(1)} KB) ready for extraction.`);
  }

  async function handleUploadAndExtract() {
    if (!selectedWs) {
      setMessage("Please select or create a workspace first.");
      return;
    }
    if (!selectedClient) {
      setMessage("Please select or create a client brand space before uploading guidelines.");
      return;
    }
    if (!selectedFile && !guidelineText.trim()) {
      setMessage("Please choose a guideline document (.txt, .md, .docx, .pdf) or paste guideline text to extract rules.");
      return;
    }

    setLoading(true);
    setIsExtracting(true);
    const docTitle = selectedFile ? selectedFile.name : "Core Brand Guidelines";
    setMessage(`Uploading '${docTitle}' and extracting candidate rules via Gemini...`);
    try {
      const formData = new FormData();
      if (selectedFile) {
        formData.append("title", selectedFile.name);
        formData.append("file", selectedFile, selectedFile.name);
      } else {
        formData.append("title", "Core Brand Guidelines");
        formData.append(
          "file",
          new Blob([guidelineText], { type: "text/plain" }),
          "guidelines.txt"
        );
      }

      const res = await api.post<{ candidate_count?: number }>(
        `/api/v1/workspaces/${selectedWs}/clients/${selectedClient}/documents`,
        formData
      );
      await loadCandidates();
      if (selectedFile) {
        setSelectedFile(null);
        if (fileInputRef.current) fileInputRef.current.value = "";
      }
      setMessage(
        `Guideline document '${docTitle}' processed! Extracted ${res?.candidate_count ?? 0} candidate rules ready for review.`
      );
    } catch (err: any) {
      const detail = err?.problem?.detail || err?.message || String(err);
      setMessage(`Guideline extraction failed: ${detail}`);
    } finally {
      setLoading(false);
      setIsExtracting(false);
    }
  }

  async function handleApproveAndActivate() {
    if (!selectedWs || !selectedClient) {
      setMessage("Please select a workspace and client brand first.");
      return;
    }

    // Filter to pending candidates only (Task 3)
    const pendingCandidates = candidates.filter(
      (c) => c.review_status === "PENDING_REVIEW" || c.review_status === "MODIFIED_APPROVED"
    );
    const approvedCandidates = candidates.filter((c) => c.review_status === "APPROVED");

    if (pendingCandidates.length === 0 && approvedCandidates.length === 0) {
      setMessage("No candidate rules available to approve or activate.");
      return;
    }

    setLoading(true);
    try {
      // 1. Approve pending candidates if any
      if (pendingCandidates.length > 0) {
        const candIds = pendingCandidates.map((c) => c.candidate_id);
        await api.post(
          `/api/v1/workspaces/${selectedWs}/clients/${selectedClient}/knowledge/approve`,
          { candidate_ids: candIds }
        );
      }

      // 2. Generate dynamic unique version tag (Task 3: remove hardcoded v1.0.0)
      const nextNum = (activeVersionNumber || 0) + 1;
      const dynamicVersionTag = `v1.${nextNum}.0`;

      // 3. Activate memory with unique version tag
      const actRes = await api.post<{
        snapshot_hash: string;
        version_tag: string;
        version_number: number;
      }>(
        `/api/v1/workspaces/${selectedWs}/clients/${selectedClient}/memory/activate`,
        {
          version_tag: dynamicVersionTag,
          change_summary: `Published Living Brand Memory release ${dynamicVersionTag}`,
        }
      );

      // 4. Update memory state and reload candidates
      await checkActiveMemory();
      await loadCandidates();
      setMessage(
        `Memory activated! Release: ${actRes.version_tag || dynamicVersionTag} | Snapshot SHA-256: ${actRes.snapshot_hash.slice(0, 16)}…`
      );
    } catch (err: any) {
      const detail = err?.problem?.detail || err?.message || String(err);
      setMessage(`Memory activation failed: ${detail}`);
    } finally {
      setLoading(false);
    }
  }

  function handleLoadDraft(type: "compliant" | "non-compliant") {
    // Reset all previous asset/version references and audit scorecard (Task 2)
    setCurrentAssetId(null);
    setCurrentVersionId(null);
    setCurrentVersionNumber(1);
    setLatestAudit(null);
    setLastAuditedText(null);

    if (type === "non-compliant") {
      setContentTitle("Spring Serum Launch Copy (Non-Compliant Draft)");
      setContentText("Our cheap serum is formulated with a synthetic base for glowing skin.");
      setMessage("Loaded Non-Compliant sample draft. Previous version state reset.");
    } else {
      setContentTitle("Spring Serum Launch Copy (Compliant Draft)");
      setContentText("Our accessible luxury serum features certified organic botanical extracts.");
      setMessage("Loaded Compliant sample draft. Previous version state reset.");
    }
  }

  async function handleRunAudit() {
    if (!selectedWs || !selectedClient) return;
    if (!activeSnapshotHash) {
      setMessage("Auditing disabled: An active Living Brand Memory snapshot is required before auditing content.");
      return;
    }
    setLoading(true);
    try {
      // 1. Create fresh asset/version if none or if text content changed since last version creation (Task 2)
      let aId = currentAssetId;
      let vId = currentVersionId;
      if (!aId || contentText !== lastAuditedText) {
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
        setLastAuditedText(contentText);
      }

      // 2. Trigger audit for selected draft's actual content and version
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
      setLastAuditedText(res.text_content);

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
      const reviewItem = reviews.find((r) => r.review_id === revId);
      if (!reviewItem) {
        setMessage("Approval failed: Review request not found in active review queue.");
        return;
      }
      if (!reviewItem.audit_run_id) {
        setMessage("Approval failed: Review request is missing an associated audit run identifier.");
        return;
      }

      // Retrieve findings specifically associated with this review's audit run (A2)
      let acknowledgedFindingIds: string[] = [];
      try {
        const auditRunData = await api.get<AuditRun>(
          `/api/v1/workspaces/${selectedWs}/clients/${selectedClient}/audits/${reviewItem.audit_run_id}`
        );
        if (!auditRunData || !Array.isArray(auditRunData.findings)) {
          throw new Error("Audit data returned from server is missing findings list.");
        }
        acknowledgedFindingIds = auditRunData.findings
          .filter((finding) => ["MAJOR", "MINOR", "ADVISORY"].includes(finding.severity))
          .map((finding) => finding.finding_id);
      } catch (fetchErr) {
        setMessage(`Approval failed: Unable to fetch audit findings for review: ${String(fetchErr)}`);
        return;
      }

      await api.post(
        `/api/v1/workspaces/${selectedWs}/clients/${selectedClient}/reviews/${revId}/decision`,
        {
          decision: "APPROVED",
          decision_notes: "Verified against living brand memory snapshot.",
          advisory_acknowledgments: acknowledgedFindingIds,
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
                onChange={(e) => handleWorkspaceChange(e.target.value)}
              >
                {workspaces.map((w) => (
                  <option key={w.workspace_id} value={w.workspace_id}>
                    {w.name} ({w.slug})
                  </option>
                ))}
              </select>
              <button
                type="button"
                onClick={() => {
                  setNewWorkspaceName("");
                  setShowCreateWorkspaceModal(true);
                }}
                disabled={loading}
                className="text-xs bg-gray-100 hover:bg-gray-200 border rounded px-2 py-1"
                title="Create a new agency workspace"
              >
                + New
              </button>
              {selectedWs && (
                <button
                  type="button"
                  onClick={() => {
                    const cur = workspaces.find((w) => w.workspace_id === selectedWs);
                    setRenameWorkspaceName(cur?.name || "");
                    setShowRenameWorkspaceModal(true);
                  }}
                  disabled={loading}
                  className="text-xs bg-gray-100 hover:bg-gray-200 border rounded px-2 py-1 text-gray-700"
                  title="Rename active workspace"
                >
                  Rename
                </button>
              )}
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
                type="button"
                onClick={() => setShowCreateClientModal(true)}
                disabled={loading || !selectedWs}
                className="text-xs bg-gray-100 hover:bg-gray-200 border rounded px-2 py-1"
              >
                + New
              </button>
              {selectedWs && selectedClient && clients.length > 0 && (
                <button
                  type="button"
                  onClick={() => {
                    const cur = clients.find((c) => c.client_id === selectedClient);
                    setRenameClientName(cur?.name || "");
                    setShowRenameClientModal(true);
                  }}
                  disabled={loading}
                  className="text-xs bg-gray-100 hover:bg-gray-200 border rounded px-2 py-1 text-gray-700"
                  title="Rename active client brand"
                >
                  Rename
                </button>
              )}
            </div>
          </div>
        </div>

        {/* MODAL: CREATE WORKSPACE */}
        {showCreateWorkspaceModal && (
          <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
            <div className="bg-white rounded-xl shadow-xl max-w-sm w-full p-5 space-y-4">
              <h3 className="text-sm font-semibold text-gray-900">Create Agency Workspace</h3>
              <p className="text-xs text-gray-600">
                Creates a new isolated multi-tenant agency workspace and assigns you WORKSPACE_ADMIN.
              </p>
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Workspace Name</label>
                <input
                  type="text"
                  value={newWorkspaceName}
                  onChange={(e) => setNewWorkspaceName(e.target.value)}
                  className="w-full border rounded px-2.5 py-1.5 text-xs focus:ring-1 focus:ring-indigo-500"
                  placeholder="e.g. Apex Creative Agency"
                  autoFocus
                />
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowCreateWorkspaceModal(false)}
                  className="text-xs border px-3 py-1.5 rounded hover:bg-gray-50 text-gray-600"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={() => void handleCreateWorkspaceSubmit()}
                  disabled={loading || !newWorkspaceName.trim()}
                  className="text-xs bg-indigo-600 text-white font-medium px-3 py-1.5 rounded hover:bg-indigo-700 disabled:opacity-50"
                >
                  {loading ? "Creating..." : "Create Workspace"}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* MODAL: RENAME WORKSPACE */}
        {showRenameWorkspaceModal && (
          <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
            <div className="bg-white rounded-xl shadow-xl max-w-sm w-full p-5 space-y-4">
              <h3 className="text-sm font-semibold text-gray-900">Rename Workspace</h3>
              <p className="text-xs text-gray-600">
                Update the display name of the selected workspace.
              </p>
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">New Workspace Name</label>
                <input
                  type="text"
                  value={renameWorkspaceName}
                  onChange={(e) => setRenameWorkspaceName(e.target.value)}
                  className="w-full border rounded px-2.5 py-1.5 text-xs focus:ring-1 focus:ring-indigo-500"
                  placeholder="Enter new workspace name"
                  autoFocus
                />
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowRenameWorkspaceModal(false)}
                  className="text-xs border px-3 py-1.5 rounded hover:bg-gray-50 text-gray-600"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={() => void handleRenameWorkspaceSubmit()}
                  disabled={loading || !renameWorkspaceName.trim()}
                  className="text-xs bg-indigo-600 text-white font-medium px-3 py-1.5 rounded hover:bg-indigo-700 disabled:opacity-50"
                >
                  {loading ? "Renaming..." : "Save Name"}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* MODAL: PROVISION CLIENT BRAND (Task 1) */}
        {showCreateClientModal && (
          <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
            <div className="bg-white rounded-xl shadow-xl max-w-sm w-full p-5 space-y-4">
              <h3 className="text-sm font-semibold text-gray-900">Provision Client Brand Space</h3>
              <p className="text-xs text-gray-600">
                Provisions a dedicated client brand workspace and atomically assigns you the initial BRAND_MANAGER role (ADR-003).
              </p>
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Client Brand Name</label>
                <input
                  type="text"
                  value={newClientName}
                  onChange={(e) => setNewClientName(e.target.value)}
                  className="w-full border rounded px-2.5 py-1.5 text-xs focus:ring-1 focus:ring-indigo-500"
                  placeholder="e.g. Verve Botanicals"
                  autoFocus
                />
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowCreateClientModal(false)}
                  className="text-xs border px-3 py-1.5 rounded hover:bg-gray-50 text-gray-600"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={() => void handleCreateClient()}
                  disabled={loading || !newClientName.trim()}
                  className="text-xs bg-indigo-600 text-white font-medium px-3 py-1.5 rounded hover:bg-indigo-700 disabled:opacity-50"
                >
                  {loading ? "Creating..." : "Create Client Brand"}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* MODAL: RENAME CLIENT BRAND */}
        {showRenameClientModal && (
          <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
            <div className="bg-white rounded-xl shadow-xl max-w-sm w-full p-5 space-y-4">
              <h3 className="text-sm font-semibold text-gray-900">Rename Client Brand</h3>
              <p className="text-xs text-gray-600">
                Update the display name of this client brand space.
              </p>
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Client Brand Name</label>
                <input
                  type="text"
                  value={renameClientName}
                  onChange={(e) => setRenameClientName(e.target.value)}
                  className="w-full border rounded px-2.5 py-1.5 text-xs focus:ring-1 focus:ring-indigo-500"
                  placeholder="e.g. Lumina Skincare Global"
                  autoFocus
                />
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowRenameClientModal(false)}
                  className="text-xs border px-3 py-1.5 rounded hover:bg-gray-50 text-gray-600"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={() => void handleRenameClientSubmit()}
                  disabled={loading || !renameClientName.trim()}
                  className="text-xs bg-indigo-600 text-white font-medium px-3 py-1.5 rounded hover:bg-indigo-700 disabled:opacity-50"
                >
                  {loading ? "Saving..." : "Save Name"}
                </button>
              </div>
            </div>
          </div>
        )}

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
                SHA-256: {activeSnapshotHash.slice(0, 10)}… {activeVersionTag ? `(${activeVersionTag})` : ""}
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
          structured rules across Terminology, Color, and Facts using Gemini.
        </p>

        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-3">
            <span className="text-xs font-medium text-gray-700">Guideline Document:</span>
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={loading || isExtracting}
              className="px-3 py-1.5 bg-gray-100 hover:bg-gray-200 border rounded text-xs font-medium text-gray-700 flex items-center gap-1.5"
            >
              <span>📁 Choose File</span>
            </button>
            <input
              ref={fileInputRef}
              type="file"
              accept=".txt,.md,.docx,.pdf"
              className="hidden"
              onChange={handleFileSelected}
            />
            {selectedFile ? (
              <div className="flex items-center gap-2 text-xs text-gray-700 bg-blue-50 border border-blue-200 px-2.5 py-1 rounded">
                <span className="font-semibold text-blue-900 truncate max-w-xs">{selectedFile.name}</span>
                <span className="text-blue-600 text-2xs">({(selectedFile.size / 1024).toFixed(1)} KB)</span>
                <button
                  type="button"
                  onClick={() => {
                    setSelectedFile(null);
                    if (fileInputRef.current) fileInputRef.current.value = "";
                  }}
                  className="text-red-500 hover:text-red-700 font-bold ml-1 text-xs"
                  title="Remove file"
                >
                  ✕
                </button>
              </div>
            ) : (
              <span className="text-2xs text-gray-400">Supported: .txt, .md, .docx, .pdf (max 25MB)</span>
            )}
            {isExtracting && (
              <span className="text-xs text-indigo-600 font-medium animate-pulse ml-auto">
                Extracting candidate rules via Gemini...
              </span>
            )}
          </div>

          <div className="space-y-1">
            <label className="block text-2xs font-medium text-gray-500 uppercase tracking-wider">
              Or Paste Guideline Text
            </label>
            <textarea
              rows={3}
              value={guidelineText}
              onChange={(e) => setGuidelineText(e.target.value)}
              className="w-full border rounded-lg p-2.5 font-mono text-xs bg-gray-50 focus:bg-white"
              placeholder="Paste brand guideline text directly here..."
            />
          </div>

          {!selectedClient && (
            <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 p-2 rounded">
              ⚠️ Please select or create a Client Brand above before extracting guidelines.
            </p>
          )}
        </div>

        {/* Extracted Candidates Preview (Task 4) */}
        {candidates.length > 0 && (
          <div className="border rounded-lg p-3 bg-gray-50 space-y-2">
            <div className="flex justify-between items-center">
              <span className="text-xs font-semibold text-gray-700">
                Extracted Candidate Rules ({candidates.length} total)
              </span>
              <span className="text-2xs text-gray-500">
                {candidates.filter((c) => c.review_status === "APPROVED").length} Approved |{" "}
                {
                  candidates.filter(
                    (c) =>
                      c.review_status === "PENDING_REVIEW" ||
                      c.review_status === "MODIFIED_APPROVED"
                  ).length
                }{" "}
                Pending
              </span>
            </div>
            <div className="max-h-36 overflow-y-auto space-y-1.5 pr-1">
              {candidates.slice(0, 10).map((cand) => (
                <div
                  key={cand.candidate_id}
                  className="bg-white border rounded p-2 text-xs flex justify-between items-start"
                >
                  <div className="space-y-0.5">
                    <span className="font-semibold text-indigo-900 mr-2 uppercase text-2xs">
                      [{cand.category}]
                    </span>
                    <span className="font-mono text-2xs text-gray-800">
                      {JSON.stringify(cand.payload)}
                    </span>
                  </div>
                  <span
                    className={`text-2xs px-1.5 py-0.5 rounded font-bold ${
                      cand.review_status === "APPROVED"
                        ? "bg-emerald-100 text-emerald-800"
                        : "bg-amber-100 text-amber-800"
                    }`}
                  >
                    {cand.review_status}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="flex gap-2">
          <button
            onClick={() => void handleUploadAndExtract()}
            disabled={loading || !selectedClient || isExtracting}
            className="text-xs bg-blue-600 text-white font-medium px-3 py-1.5 rounded hover:bg-blue-700 disabled:opacity-50"
          >
            {isExtracting ? "Extracting..." : "Upload & Extract Rules"}
          </button>
          {(() => {
            const pendingCount = candidates.filter(
              (c) =>
                c.review_status === "PENDING_REVIEW" ||
                c.review_status === "MODIFIED_APPROVED"
            ).length;
            const approvedCount = candidates.filter((c) => c.review_status === "APPROVED").length;
            return (
              <button
                onClick={() => void handleApproveAndActivate()}
                disabled={loading || (pendingCount === 0 && approvedCount === 0)}
                className="text-xs bg-emerald-600 text-white font-medium px-3 py-1.5 rounded hover:bg-emerald-700 disabled:opacity-50"
              >
                {pendingCount > 0
                  ? `Approve & Activate Memory Release (${pendingCount} Pending Rules)`
                  : approvedCount > 0
                  ? `Publish Memory Release (${approvedCount} Approved Rules)`
                  : "Approve & Activate Memory Release (0 Staged Candidates)"}
              </button>
            );
          })()}
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

        {/* Informative banner when auditing is disabled (Task 5) */}
        {!activeSnapshotHash && (
          <div className="bg-amber-50 border border-amber-200 text-amber-800 text-xs px-3 py-2 rounded-lg flex items-center gap-2">
            <span className="font-semibold text-amber-900">Auditing Disabled:</span>
            <span>
              No Living Brand Memory snapshot is currently active for this client brand. A Brand Manager must ingest guidelines and activate a memory snapshot in Step 1 first.
            </span>
          </div>
        )}

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
            title={!activeSnapshotHash ? "Activate a memory release in Step 1 first" : "Audit content against brand memory"}
            className="text-xs bg-indigo-600 text-white font-medium px-4 py-2 rounded hover:bg-indigo-700 disabled:opacity-50"
          >
            Run Pre-Publication Audit
          </button>
          <button
            onClick={() => handleLoadDraft("non-compliant")}
            className="text-xs border px-3 py-1.5 rounded hover:bg-gray-50 text-gray-700"
          >
            Load Non-Compliant Draft
          </button>
          <button
            onClick={() => handleLoadDraft("compliant")}
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

        {/* Separation of Duties Explanation (Task 6) */}
        <div className="bg-indigo-50 border border-indigo-200 text-indigo-950 text-xs px-3.5 py-2.5 rounded-lg space-y-1">
          <div className="font-semibold flex items-center gap-1.5">
            <span>🛡️</span>
            <span>Separation of Duties (ADR-004)</span>
          </div>
          <p className="text-gray-600">
            Content Creators cannot approve their own submissions. An independent Brand Manager must review the Diagnostic Scorecard, evaluate any advisory findings, and issue the immutable cryptographic Compliance Certificate.
          </p>
        </div>

        {reviews.length > 0 ? (
          <div className="space-y-3">
            {reviews.map((r) => {
              const currentClientRole = userProfile?.client_assignments?.find(
                (ca) => ca.client_id === selectedClient
              )?.client_role;
              const isBrandManager = currentClientRole === "BRAND_MANAGER";
              const isSubmitter = Boolean(userProfile?.user_id && r.submitted_by_user_id === userProfile.user_id);
              const canApprove = isBrandManager && !isSubmitter;

              return (
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
                    <div className="space-y-2 pt-2">
                      {!isBrandManager && (
                        <div className="text-2xs text-amber-800 bg-amber-50 border border-amber-200 px-2 py-1 rounded">
                          ⚠️ Approval restricted to Brand Managers (Separation of Duties). Your current client assignment is &lsquo;{currentClientRole || "MEMBER"}&rsquo;.
                        </div>
                      )}
                      {isSubmitter && isBrandManager && (
                        <div className="text-2xs text-amber-800 bg-amber-50 border border-amber-200 px-2 py-1 rounded">
                          ⚠️ Submitter cannot self-approve (Separation of Duties). Requires review by another Brand Manager.
                        </div>
                      )}
                      <div className="flex gap-2">
                        <button
                          onClick={() => void handleApproveReview(r.review_id)}
                          disabled={loading || !canApprove}
                          title={
                            !isBrandManager
                              ? "Only Brand Managers can approve"
                              : isSubmitter
                              ? "Submitter cannot self-approve"
                              : "Approve and issue certificate"
                          }
                          className="text-xs bg-emerald-600 text-white font-medium px-3 py-1.5 rounded hover:bg-emerald-700 disabled:opacity-40"
                        >
                          Approve & Issue Certificate
                        </button>
                        <button
                          onClick={() => void handleRequestChangesReview(r.review_id)}
                          disabled={loading || !canApprove}
                          className="text-xs bg-blue-600 text-white font-medium px-3 py-1.5 rounded hover:bg-blue-700 disabled:opacity-40"
                        >
                          Request Changes
                        </button>
                        <button
                          onClick={() => void handleRejectReview(r.review_id)}
                          disabled={loading || !canApprove}
                          className="text-xs bg-red-600 text-white font-medium px-3 py-1.5 rounded hover:bg-red-700 disabled:opacity-40"
                        >
                          Reject
                        </button>
                      </div>
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
              );
            })}
          </div>
        ) : (
          <p className="text-xs text-gray-500 italic">No approval requests in the review queue.</p>
        )}
      </div>
    </div>
  );
}
