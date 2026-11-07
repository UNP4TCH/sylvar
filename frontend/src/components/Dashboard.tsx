import ApiStatus from "./ApiStatus";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { getSupabase } from "../lib/supabase";
import { createAuthedClient } from "../lib/authedApi";
import {
  classifyCandidate,
  getActivationBlockReason,
  getUploadBlockReason,
  nextVersionTag,
  summarizeCandidates,
  type LoadStatus,
} from "../lib/dashboardLogic";
import { formatApiError } from "../lib/errors";
import {
  validateGuidelineFile,
  GUIDELINE_ACCEPT,
  formatFileSize,
} from "../lib/guidelineFile";
import { createLatestGuard } from "../lib/latestGuard";

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

type LoadErrorKey = "profile" | "workspaces" | "clients" | "memory" | "candidates" | "reviews";

export default function Dashboard({
  apiBaseUrl,
  sessionUserEmail,
  onSignOut,
}: {
  apiBaseUrl: string;
  sessionUserEmail?: string;
  onSignOut?: () => void;
}) {
  const [userProfile, setUserProfile] = useState<UserProfile | null>(null);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [selectedWs, setSelectedWs] = useState<string>(() => localStorage.getItem("sylvar_selected_workspace") || "");
  const [showCreateWorkspaceModal, setShowCreateWorkspaceModal] = useState(false);
  const [newWorkspaceName, setNewWorkspaceName] = useState("");
  const [showRenameWorkspaceModal, setShowRenameWorkspaceModal] = useState(false);
  const [renameWorkspaceName, setRenameWorkspaceName] = useState("");

  const [clients, setClients] = useState<ClientBrand[]>([]);
  const [selectedClient, setSelectedClient] = useState<string>(() => localStorage.getItem("sylvar_selected_client") || "");
  const [showCreateClientModal, setShowCreateClientModal] = useState(false);
  const [newClientName, setNewClientName] = useState("Verve Botanicals");
  const [showRenameClientModal, setShowRenameClientModal] = useState(false);
  const [renameClientName, setRenameClientName] = useState("");

  // Load status & visible errors
  const [workspacesStatus, setWorkspacesStatus] = useState<LoadStatus>("idle");
  const [clientsStatus, setClientsStatus] = useState<LoadStatus>("idle");
  const [memoryStatus, setMemoryStatus] = useState<LoadStatus>("idle");
  const [loadErrors, setLoadErrors] = useState<Record<LoadErrorKey, string | null>>({
    profile: null,
    workspaces: null,
    clients: null,
    memory: null,
    candidates: null,
    reviews: null,
  });

  function setLoadError(key: LoadErrorKey, value: string | null) {
    setLoadErrors((prev) => (prev[key] === value ? prev : { ...prev, [key]: value }));
  }

  // File Upload & Guidelines
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [fileInputKey, setFileInputKey] = useState(0);

  // Memory & Ingestion state
  const [guidelineText, setGuidelineText] = useState(
    "Never say 'cheap' or 'synthetic'. Always emphasize 'clean luxury' and 'botanical radiance'."
  );
  const [candidates, setCandidates] = useState<ExtractedCandidate[]>([]);
  const [activeSnapshotHash, setActiveSnapshotHash] = useState<string | null>(null);
  const [activeVersionNumber, setActiveVersionNumber] = useState<number | null>(null);
  const [activeVersionTag, setActiveVersionTag] = useState<string | null>(null);
  const [isExtracting, setIsExtracting] = useState(false);

  // Content & Audit state
  const [contentTitle, setContentTitle] = useState("Launch Campaign Copy");
  const [contentText, setContentText] = useState("Our cheap serum is formulated with a synthetic base for glowing skin.");
  const [contentFormat, setContentFormat] = useState<"SOCIAL_MEDIA" | "ADVERTISEMENT" | "BLOG" | "EMAIL">("SOCIAL_MEDIA");
  const [currentAssetId, setCurrentAssetId] = useState<string | null>(null);
  const [currentVersionId, setCurrentVersionId] = useState<string | null>(null);
  const [currentVersionNumber, setCurrentVersionNumber] = useState<number>(1);
  const [latestAudit, setLatestAudit] = useState<AuditRun | null>(null);
  const [lastAuditedText, setLastAuditedText] = useState<string | null>(null);

  // Review & Compliance state
  const [reviews, setReviews] = useState<ReviewItem[]>([]);
  const [reviewAction, setReviewAction] = useState<{
    revId: string;
    action: "REJECT" | "REQUEST_CHANGES";
  } | null>(null);
  const [reviewActionNotes, setReviewActionNotes] = useState("");
  const [reviewActionError, setReviewActionError] = useState<string | null>(null);

  // Team & Member Modal
  const [showMemberModal, setShowMemberModal] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("CONTENT_CREATOR");

  // UI Navigation Pipeline Stage Filter ("ALL" | "MEMORY" | "AUDIT" | "GOVERNANCE")
  const [activePipelineTab, setActivePipelineTab] = useState<"ALL" | "MEMORY" | "AUDIT" | "GOVERNANCE">("ALL");

  // Global notifications & loading state
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // Stale-response guards
  const wsGuard = useRef(createLatestGuard());
  const clientsGuard = useRef(createLatestGuard());
  const memoryGuard = useRef(createLatestGuard());
  const candidatesGuard = useRef(createLatestGuard());
  const reviewsGuard = useRef(createLatestGuard());
  const ctxRef = useRef({ wsId: selectedWs, clientId: selectedClient });
  ctxRef.current = { wsId: selectedWs, clientId: selectedClient };

  function ctxMatches(wsId: string, clientId?: string): boolean {
    const cur = ctxRef.current;
    if (cur.wsId !== wsId) return false;
    if (clientId !== undefined && cur.clientId !== clientId) return false;
    return true;
  }

  function resetClientScoped() {
    memoryGuard.current.invalidate();
    candidatesGuard.current.invalidate();
    reviewsGuard.current.invalidate();
    setActiveSnapshotHash(null);
    setActiveVersionNumber(null);
    setActiveVersionTag(null);
    setCandidates([]);
    setReviews([]);
    setLatestAudit(null);
    setCurrentAssetId(null);
    setCurrentVersionId(null);
    setCurrentVersionNumber(1);
    setLastAuditedText(null);
    setSelectedFile(null);
    setFileError(null);
    setFileInputKey((k) => k + 1);
    setLoadError("memory", null);
    setLoadError("candidates", null);
    setLoadError("reviews", null);
  }

  const api = createAuthedClient(getSupabase, apiBaseUrl);

  useEffect(() => {
    void loadUserProfile();
    void loadWorkspaces();
  }, []);

  useEffect(() => {
    if (selectedWs) {
      localStorage.setItem("sylvar_selected_workspace", selectedWs);
      void loadClients(selectedWs);
    } else {
      localStorage.removeItem("sylvar_selected_workspace");
      setClients([]);
      setSelectedClient("");
      resetClientScoped();
    }
  }, [selectedWs]);

  useEffect(() => {
    if (selectedWs && selectedClient) {
      localStorage.setItem("sylvar_selected_client", selectedClient);
      void checkActiveMemory();
      void loadCandidates();
      void loadReviews();
    } else {
      localStorage.removeItem("sylvar_selected_client");
      resetClientScoped();
    }
  }, [selectedWs, selectedClient]);

  async function loadUserProfile() {
    setLoadError("profile", null);
    try {
      const res = await api.get<UserProfile>("/api/v1/users/me");
      setUserProfile(res);
    } catch (err) {
      setLoadError("profile", `User profile failed to load: ${formatApiError(err)}`);
    }
  }

  async function loadWorkspaces() {
    const isLatest = wsGuard.current.next();
    setWorkspacesStatus("loading");
    setLoadError("workspaces", null);
    try {
      const list = await api.get<Workspace[]>("/api/v1/workspaces");
      if (!isLatest()) return;
      setWorkspaces(list);
      setWorkspacesStatus("loaded");
      if (list.length > 0) {
        if (!selectedWs || !list.some((w) => w.workspace_id === selectedWs)) {
          setSelectedWs(list[0].workspace_id);
        }
      } else {
        setSelectedWs("");
      }
    } catch (err) {
      if (!isLatest()) return;
      setWorkspacesStatus("error");
      setLoadError("workspaces", `Workspaces failed to load: ${formatApiError(err)}`);
    }
  }

  async function loadClients(wsId: string) {
    const isLatest = clientsGuard.current.next();
    setClientsStatus("loading");
    setLoadError("clients", null);
    try {
      const list = await api.get<ClientBrand[]>(`/api/v1/workspaces/${wsId}/clients`);
      if (!isLatest() || !ctxMatches(wsId)) return;
      setClients(list);
      setClientsStatus("loaded");
      if (list.length > 0) {
        if (!selectedClient || !list.some((c) => c.client_id === selectedClient)) {
          setSelectedClient(list[0].client_id);
        }
      } else {
        setSelectedClient("");
      }
    } catch (err) {
      if (!isLatest() || !ctxMatches(wsId)) return;
      setClientsStatus("error");
      setLoadError("clients", `Client brands failed to load: ${formatApiError(err)}`);
    }
  }

  async function checkActiveMemory() {
    if (!selectedWs || !selectedClient) return;
    const wsId = selectedWs;
    const clientId = selectedClient;
    const isLatest = memoryGuard.current.next();
    setMemoryStatus("loading");
    setLoadError("memory", null);
    try {
      const res = await api.get<{
        active: boolean;
        snapshot: { snapshot_hash: string } | null;
        version: { version_number: number; version_tag: string } | null;
      }>(`/api/v1/workspaces/${wsId}/clients/${clientId}/memory/active`);
      if (!isLatest() || !ctxMatches(wsId, clientId)) return;
      if (res.active && res.snapshot) {
        setActiveSnapshotHash(res.snapshot.snapshot_hash);
        setActiveVersionNumber(res.version?.version_number ?? null);
        setActiveVersionTag(res.version?.version_tag ?? null);
      } else {
        setActiveSnapshotHash(null);
        setActiveVersionNumber(null);
        setActiveVersionTag(null);
      }
      setMemoryStatus("loaded");
    } catch (err) {
      if (!isLatest() || !ctxMatches(wsId, clientId)) return;
      setMemoryStatus("error");
      setLoadError("memory", `Active memory check failed: ${formatApiError(err)}`);
    }
  }

  async function loadCandidates() {
    if (!selectedWs || !selectedClient) return;
    const wsId = selectedWs;
    const clientId = selectedClient;
    const isLatest = candidatesGuard.current.next();
    setLoadError("candidates", null);
    try {
      const list = await api.get<ExtractedCandidate[]>(
        `/api/v1/workspaces/${wsId}/clients/${clientId}/candidates`
      );
      if (!isLatest() || !ctxMatches(wsId, clientId)) return;
      setCandidates(list);
    } catch (err) {
      if (!isLatest() || !ctxMatches(wsId, clientId)) return;
      setLoadError("candidates", `Candidates failed to load: ${formatApiError(err)}`);
    }
  }

  async function loadReviews() {
    if (!selectedWs || !selectedClient) return;
    const wsId = selectedWs;
    const clientId = selectedClient;
    const isLatest = reviewsGuard.current.next();
    setLoadError("reviews", null);
    try {
      const list = await api.get<ReviewItem[]>(
        `/api/v1/workspaces/${wsId}/clients/${clientId}/reviews`
      );
      if (!isLatest() || !ctxMatches(wsId, clientId)) return;
      setReviews(list);
    } catch (err) {
      if (!isLatest() || !ctxMatches(wsId, clientId)) return;
      setLoadError("reviews", `Review queue failed to load: ${formatApiError(err)}`);
    }
  }

  function handleWorkspaceChange(newWsId: string) {
    if (newWsId === selectedWs) return;
    setSelectedWs(newWsId);
    setSelectedClient("");
    resetClientScoped();
  }

  function handleClientChange(newClientId: string) {
    if (newClientId === selectedClient) return;
    setSelectedClient(newClientId);
    resetClientScoped();
  }

  async function handleCreateWorkspaceSubmit(e: FormEvent) {
    e.preventDefault();
    if (!newWorkspaceName.trim()) return;
    setLoading(true);
    try {
      const res = await api.post<Workspace>("/api/v1/workspaces", {
        name: newWorkspaceName.trim(),
      });
      setNewWorkspaceName("");
      setShowCreateWorkspaceModal(false);
      setMessage(`Workspace '${res.name}' created successfully.`);
      await loadWorkspaces();
      setSelectedWs(res.workspace_id);
    } catch (err) {
      setMessage(`Failed to create workspace: ${formatApiError(err)}`);
    } finally {
      setLoading(false);
    }
  }

  async function handleRenameWorkspaceSubmit(e: FormEvent) {
    e.preventDefault();
    if (!selectedWs || !renameWorkspaceName.trim()) return;
    setLoading(true);
    try {
      const res = await api.patch<Workspace>(`/api/v1/workspaces/${selectedWs}`, {
        name: renameWorkspaceName.trim(),
      });
      setShowRenameWorkspaceModal(false);
      setMessage(`Workspace renamed to '${res.name}'.`);
      await loadWorkspaces();
    } catch (err) {
      setMessage(`Failed to rename workspace: ${formatApiError(err)}`);
    } finally {
      setLoading(false);
    }
  }

  async function handleCreateClient() {
    if (!selectedWs || !newClientName.trim()) return;
    setLoading(true);
    try {
      const res = await api.post<ClientBrand>(`/api/v1/workspaces/${selectedWs}/clients`, {
        name: newClientName.trim(),
      });
      setShowCreateClientModal(false);
      setNewClientName("Verve Botanicals");
      setMessage(`Client brand '${res.name}' created and scoped.`);
      await loadClients(selectedWs);
      setSelectedClient(res.client_id);
      await loadUserProfile();
    } catch (err) {
      setMessage(`Failed to provision client brand: ${formatApiError(err)}`);
    } finally {
      setLoading(false);
    }
  }

  async function handleRenameClientSubmit() {
    if (!selectedWs || !selectedClient || !renameClientName.trim()) return;
    setLoading(true);
    try {
      const res = await api.patch<ClientBrand>(
        `/api/v1/workspaces/${selectedWs}/clients/${selectedClient}`,
        { name: renameClientName.trim() }
      );
      setShowRenameClientModal(false);
      setMessage(`Client brand renamed to '${res.name}'.`);
      await loadClients(selectedWs);
    } catch (err) {
      setMessage(`Failed to rename client brand: ${formatApiError(err)}`);
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
        client_id: selectedClient || null,
      });
      setMessage(`Invitation sent to ${inviteEmail} as ${inviteRole}.`);
      setInviteEmail("");
      setShowMemberModal(false);
    } catch (err) {
      setMessage(`Failed to add team member: ${formatApiError(err)}`);
    } finally {
      setLoading(false);
    }
  }

  function handleFileSelected(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const v = validateGuidelineFile(file);
    if (!v.ok) {
      setSelectedFile(null);
      setFileError(v.error);
      setFileInputKey((k) => k + 1);
      return;
    }
    setFileError(null);
    setSelectedFile(file);
  }

  function clearSelectedFile() {
    setSelectedFile(null);
    setFileError(null);
    setFileInputKey((k) => k + 1);
  }

  async function handleUploadAndExtract() {
    if (!selectedWs || !selectedClient) return;

    if (selectedFile) {
      setLoading(true);
      setIsExtracting(true);
      setMessage(`Uploading '${selectedFile.name}' and extracting candidate rules via Gemini...`);
      try {
        const formData = new FormData();
        formData.append("title", selectedFile.name);
        formData.append("file", selectedFile, selectedFile.name);

        const res = await api.post<{ candidate_count?: number }>(
          `/api/v1/workspaces/${selectedWs}/clients/${selectedClient}/documents`,
          formData
        );
        await loadCandidates();
        setMessage(
          `Extracted ${res?.candidate_count ?? "new"} candidate rule(s) from '${selectedFile.name}'.`
        );
        clearSelectedFile();
      } catch (err) {
        setMessage(`File upload failed: ${formatApiError(err)}`);
      } finally {
        setLoading(false);
        setIsExtracting(false);
      }
      return;
    }

    if (!guidelineText.trim()) return;
    setLoading(true);
    setIsExtracting(true);
    setMessage("Processing brand guideline text and extracting rules via Gemini...");
    try {
      const formData = new FormData();
      formData.append("title", "Pasted Brand Guidelines");
      formData.append(
        "file",
        new Blob([guidelineText], { type: "text/plain" }),
        "pasted_guidelines.txt"
      );

      const res = await api.post<{ candidate_count?: number }>(
        `/api/v1/workspaces/${selectedWs}/clients/${selectedClient}/documents`,
        formData
      );
      await loadCandidates();
      setMessage(
        `Extracted ${res?.candidate_count ?? "new"} candidate rule(s) from pasted guidelines.`
      );
    } catch (err) {
      setMessage(`Extraction failed: ${formatApiError(err)}`);
    } finally {
      setLoading(false);
      setIsExtracting(false);
    }
  }

  async function handleApproveAndActivate() {
    if (!selectedWs || !selectedClient) return;

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
      if (pendingCandidates.length > 0) {
        const candIds = pendingCandidates.map((c) => c.candidate_id);
        await api.post(
          `/api/v1/workspaces/${selectedWs}/clients/${selectedClient}/knowledge/approve`,
          { candidate_ids: candIds }
        );
      }

      const dynamicVersionTag = nextVersionTag(activeVersionNumber);

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

      await checkActiveMemory();
      await loadCandidates();
      setMessage(
        `Memory activated! Release: ${actRes.version_tag || dynamicVersionTag} | Snapshot SHA-256: ${actRes.snapshot_hash.slice(0, 16)}…`
      );
    } catch (err) {
      setMessage(`Memory activation failed: ${formatApiError(err)}`);
    } finally {
      setLoading(false);
    }
  }

  function handleFormatChange(fmt: "SOCIAL_MEDIA" | "ADVERTISEMENT" | "BLOG" | "EMAIL") {
    setContentFormat(fmt);
    setCurrentAssetId(null);
    setCurrentVersionId(null);
    setCurrentVersionNumber(1);
    setLatestAudit(null);
    setLastAuditedText(null);

    const templates: Record<typeof fmt, { title: string; text: string }> = {
      SOCIAL_MEDIA: {
        title: "Instagram Launch Post (Spring Radiance)",
        text: "Say goodbye to cheap skincare! Our synthetic booster gives you instant glow. #SkinCare #Beauty",
      },
      ADVERTISEMENT: {
        title: "Digital Display Ad Headline & Subcopy",
        text: "Cheap solutions don't last. Upgrade to our laboratory synthetic formula for radiant skin.",
      },
      BLOG: {
        title: "Blog: 5 Reasons to Choose Clean Luxury",
        text: "Many cheap serums cut corners using synthetic additives that mask underlying skin vitality.",
      },
      EMAIL: {
        title: "VIP Customer Launch Newsletter",
        text: "Dear VIP, avoid cheap alternatives. Discover our synthetic-powered glow treatment today.",
      },
    };
    const t = templates[fmt];
    setContentTitle(t.title);
    setContentText(t.text);
    setMessage(`Switched channel format to ${fmt}. Loaded template draft.`);
  }

  function handleLoadDraft(type: "compliant" | "non-compliant") {
    setCurrentAssetId(null);
    setCurrentVersionId(null);
    setCurrentVersionNumber(1);
    setLatestAudit(null);
    setLastAuditedText(null);

    if (type === "non-compliant") {
      setContentTitle("Spring Serum Launch Copy (Non-Compliant Draft)");
      setContentText("Our cheap serum is formulated with a synthetic base for glowing skin.");
      setMessage("Loaded Non-Compliant sample draft. Ready for pre-publication audit.");
    } else {
      setContentTitle("Spring Serum Launch Copy (Compliant Draft)");
      setContentText("Our accessible luxury serum features certified organic botanical radiance.");
      setMessage("Loaded Compliant sample draft. Ready for pre-publication audit.");
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

      const auditRes = await api.post<AuditRun>(
        `/api/v1/workspaces/${selectedWs}/clients/${selectedClient}/assets/${aId}/versions/${vId}/audit`
      );
      setLatestAudit(auditRes);
      setMessage(`Audit completed with verdict: ${auditRes.overall_verdict}`);
    } catch (err) {
      setMessage(`Audit execution failed: ${formatApiError(err)}`);
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
        `/api/v1/workspaces/${selectedWs}/clients/${selectedClient}/assets/${latestAudit.asset_id}/versions/${latestAudit.asset_version_id}/remediate`,
        {
          correction_ids: [suggId],
          author_id: userProfile?.user_id,
        }
      );
      setContentText(res.text_content);
      setCurrentVersionId(res.version_id);
      setCurrentVersionNumber(res.version_number);
      setLastAuditedText(res.text_content);

      const reAudit = await api.post<AuditRun>(
        `/api/v1/workspaces/${selectedWs}/clients/${selectedClient}/assets/${latestAudit.asset_id}/versions/${res.version_id}/audit`
      );
      setLatestAudit(reAudit);
      setMessage(`Surgical fix applied! Created Version ${res.version_number}. Re-audit verdict: ${reAudit.overall_verdict}`);
    } catch (err) {
      setMessage(`Remediation failed: ${formatApiError(err)}`);
    } finally {
      setLoading(false);
    }
  }

  async function handleSubmitReview() {
    if (!selectedWs || !selectedClient || !latestAudit) return;
    setLoading(true);
    try {
      await api.post(`/api/v1/workspaces/${selectedWs}/clients/${selectedClient}/reviews`, {
        asset_id: latestAudit.asset_id,
        asset_version_id: latestAudit.asset_version_id,
        audit_run_id: latestAudit.audit_run_id,
      });
      await loadReviews();
      setMessage("Clean asset version submitted to Brand Manager review queue.");
    } catch (err) {
      setMessage(`Review submission failed: ${formatApiError(err)}`);
    } finally {
      setLoading(false);
    }
  }

  async function handleApproveReview(revId: string) {
    if (!selectedWs || !selectedClient) return;
    setLoading(true);
    try {
      const res = await api.post<{
        status: string;
        certificate: NonNullable<ReviewItem["certificate"]>;
      }>(
        `/api/v1/workspaces/${selectedWs}/clients/${selectedClient}/reviews/${revId}/decision`,
        {
          decision: "APPROVED",
          decision_notes: "Brand integrity verified against Living Memory snapshot.",
          advisory_acknowledgments: [],
        }
      );
      await loadReviews();
      setMessage(`Review approved! Issued Compliance Certificate SHA-256: ${res.certificate.certificate_hash.slice(0, 16)}…`);
    } catch (err) {
      setMessage(`Approval failed: ${formatApiError(err)}`);
    } finally {
      setLoading(false);
    }
  }

  function openReviewActionModal(revId: string, action: "REJECT" | "REQUEST_CHANGES") {
    setReviewAction({ revId, action });
    setReviewActionNotes(
      action === "REJECT"
        ? "Rejected due to brand guideline non-compliance."
        : "Please refine claim substantiation and resubmit."
    );
    setReviewActionError(null);
  }

  function handleRejectReview(revId: string) {
    openReviewActionModal(revId, "REJECT");
  }

  function handleRequestChangesReview(revId: string) {
    openReviewActionModal(revId, "REQUEST_CHANGES");
  }

  async function submitReviewAction() {
    if (!reviewAction) return;
    if (!reviewActionNotes.trim()) {
      setReviewActionError("Reviewer comments are mandatory when rejecting or requesting changes.");
      return;
    }
    if (!selectedWs || !selectedClient) return;
    setLoading(true);
    setReviewActionError(null);
    try {
      await api.post(
        `/api/v1/workspaces/${selectedWs}/clients/${selectedClient}/reviews/${reviewAction.revId}/decision`,
        {
          decision: reviewAction.action === "REJECT" ? "REJECTED" : "CHANGES_REQUESTED",
          decision_notes: reviewActionNotes.trim(),
          advisory_acknowledgments: [],
        }
      );
      const actionName = reviewAction.action === "REJECT" ? "REJECTED" : "CHANGES_REQUESTED";
      setReviewAction(null);
      setReviewActionNotes("");
      setReviewActionError(null);
      await loadReviews();
      setMessage(`Review request status updated to ${actionName}. Mandatory feedback recorded.`);
    } catch (err) {
      setReviewActionError(`Action failed: ${formatApiError(err)}`);
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

  const uploadBlockReason = getUploadBlockReason({
    selectedWs,
    selectedClient,
    workspacesStatus,
    clientsStatus,
    workspacesError: loadErrors.workspaces,
    clientsError: loadErrors.clients,
  });
  const candidateSummary = summarizeCandidates(candidates);
  const activationBlockReason = getActivationBlockReason({
    memoryStatus,
    memoryError: loadErrors.memory,
    summary: candidateSummary,
  });

  // User assignments in active client
  const currentClientAssignment = userProfile?.client_assignments?.find(
    (ca) => ca.client_id === selectedClient
  );
  const currentClientRole = currentClientAssignment?.client_role || "CONTENT_CREATOR";
  const isBrandManager = currentClientRole === "BRAND_MANAGER";

  const pageMeta = {
    ALL: { eyebrow: "WORKSPACE OVERVIEW", title: "Good to see you.", description: "Your brand governance workspace at a glance." },
    MEMORY: { eyebrow: "STAGE 01 · LIVING BRAND MEMORY", title: "Brand memory", description: "Manage approved guidelines, extracted rules and active brand knowledge." },
    AUDIT: { eyebrow: "STAGE 02 · CONTENT GOVERNANCE", title: "Governance studio", description: "Create content, run pre-publication audits and resolve findings." },
    GOVERNANCE: { eyebrow: "STAGE 03 · INDEPENDENT REVIEW", title: "Review queue", description: "Review submissions, record decisions and issue compliance certificates." },
  }[activePipelineTab];

  return (
    <div className="sylvar-dashboard-shell">
      <aside className="sylvar-sidebar">
        <div className="sylvar-brand-lockup"><span className="sylvar-brand-mark">S</span><span><strong>SYLVAR</strong><small>BRAND INTEGRITY PLATFORM</small></span></div>
        <div className="sylvar-sidebar-section-label">WORKSPACE</div>
        <div className="sylvar-sidebar-context">
          <span className="sylvar-context-dot" />
          <span className="sylvar-context-copy"><strong>{workspaces.find((w) => w.workspace_id === selectedWs)?.name || "Select workspace"}</strong><small>{clients.find((c) => c.client_id === selectedClient)?.name || "No client selected"}</small></span>
        </div>
        <div className="sylvar-sidebar-section-label">GOVERNANCE</div>
        <nav className="sylvar-side-nav" aria-label="Main navigation">
          <button type="button" className={activePipelineTab === "ALL" ? "active" : ""} onClick={() => setActivePipelineTab("ALL")}><span className="nav-icon">⌂</span>Overview</button>
          <button type="button" className={activePipelineTab === "MEMORY" ? "active" : ""} onClick={() => setActivePipelineTab("MEMORY")}><span className="nav-icon">◈</span>Living memory{candidateSummary.pending > 0 && <i>{candidateSummary.pending}</i>}</button>
          <button type="button" className={activePipelineTab === "AUDIT" ? "active" : ""} onClick={() => setActivePipelineTab("AUDIT")}><span className="nav-icon">✳</span>Governance studio</button>
          <button type="button" className={activePipelineTab === "GOVERNANCE" ? "active" : ""} onClick={() => setActivePipelineTab("GOVERNANCE")}><span className="nav-icon">▤</span>Review queue{reviews.length > 0 && <i>{reviews.length}</i>}</button>
        </nav>
        <div className="sylvar-sidebar-bottom">
          <div className="sylvar-sidebar-status"><span className="sylvar-live-dot"/> API CONNECTED</div>
          <div className="sylvar-sidebar-user">
            <span className="sylvar-user-avatar">{(userProfile?.email || "S").slice(0, 1).toUpperCase()}</span>
            <span>
              <strong>{userProfile?.email || "Workspace Member"}</strong>
              <small>Authenticated session</small>
            </span>
          </div>
        </div>
      </aside>
      <main className="sylvar-dashboard-main">
        <header className="sylvar-dashboard-topbar">
          <div>
            <span className="sylvar-topbar-kicker">SYLVAR <span>/</span> {pageMeta.eyebrow}</span>
            <h1>{pageMeta.title}</h1>
            <p>{pageMeta.description}</p>
          </div>
          <div className="sylvar-topbar-actions">
            <ApiStatus baseUrl={apiBaseUrl} />
            <button
              type="button"
              className="sylvar-btn-outline px-3 py-1.5 rounded-md text-xs font-medium cursor-pointer"
              onClick={() => setShowMemberModal(true)}
              disabled={!selectedWs}
            >
              Team & access
            </button>
            <div className="flex items-center gap-2 bg-[#151418] border border-[#28242f] rounded-md py-1 px-3 text-xs">
              <span className="h-1.5 w-1.5 rounded-full bg-[#4ade80]" />
              <span className="text-[#dfd4cc] font-medium">{sessionUserEmail || userProfile?.email || "Signed in"}</span>
            </div>
            {onSignOut && (
              <button
                type="button"
                className="sylvar-btn-secondary px-3 py-1.5 rounded-md text-xs font-medium cursor-pointer"
                onClick={onSignOut}
              >
                Sign out
              </button>
            )}
          </div>
        </header>
        <div className="sylvar-dashboard-content space-y-6">
      {/* GLOBAL TOAST / ALERT NOTIFICATION */}
      {message && (
        <div
          role="status"
          className="p-3.5 bg-[#181620] border border-[#3b324a] text-[#f0eaf8] rounded-md text-xs sm:text-sm flex justify-between items-center gap-3 transition-all"
        >
          <div className="flex items-center gap-2.5">
            <span className="flex h-2 w-2 rounded-full bg-[#f59e0b]" />
            <span className="font-medium">{message}</span>
          </div>
          <button
            onClick={() => setMessage(null)}
            className="text-xs font-semibold px-2.5 py-1 text-[#f59e0b] hover:bg-[#25202e] rounded-md transition-colors cursor-pointer"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* ERROR BANNERS (SHOWN, NEVER SWALLOWED) */}
      {(
        [
          ["profile", null],
          ["workspaces", () => void loadWorkspaces()],
          ["clients", () => selectedWs && void loadClients(selectedWs)],
          ["memory", () => void checkActiveMemory()],
          ["candidates", () => void loadCandidates()],
          ["reviews", () => void loadReviews()],
        ] as Array<[LoadErrorKey, (() => void) | null]>
      ).map(([key, retry]) =>
        loadErrors[key] ? (
          <div
            key={key}
            role="alert"
            className="p-3 bg-[#241719] border border-[#522b31] text-[#fca5a5] rounded-md text-xs sm:text-sm flex justify-between items-center gap-3"
          >
            <div className="flex items-center gap-2">
              <span className="font-bold">Error:</span>
              <span>{loadErrors[key]}</span>
            </div>
            {retry && (
              <button
                onClick={retry}
                className="text-xs font-semibold px-2.5 py-1 bg-[#1a1315] border border-[#6b353d] text-[#fecaca] hover:bg-[#2f1b20] rounded-md transition-colors cursor-pointer shrink-0"
              >
                Retry
              </button>
            )}
          </div>
        ) : null
      )}

      {/* TOP CONTROL BAR: Multi-Tenant Workspace & Client Scoping */}
      <div className="bg-[#131215] rounded-lg border border-[#232027] p-4">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
          <div className="flex flex-wrap items-center gap-4 sm:gap-6">
            {/* Workspace Scoping */}
            <div>
              <span className="block text-xs font-medium text-[#9a928c] mb-1.5">
                Agency Workspace
              </span>
              <div className="flex items-center gap-2">
                <select
                  className="rounded-md border border-[#2d2833] bg-[#161518] px-3 py-1.5 text-xs font-medium text-[#f1eae4] focus:border-[#f59e0b] focus:outline-none transition-all"
                  value={selectedWs}
                  onChange={(e) => handleWorkspaceChange(e.target.value)}
                  aria-label="Workspace"
                >
                  {workspaces.length === 0 && (
                    <option value="">
                      {workspacesStatus === "loading"
                        ? "Loading workspaces…"
                        : workspacesStatus === "error"
                        ? "Workspaces failed to load"
                        : "No workspaces"}
                    </option>
                  )}
                  {workspaces.map((w) => (
                    <option key={w.workspace_id} value={w.workspace_id}>
                      {w.name}
                    </option>
                  ))}
                </select>
                <button
                  onClick={() => setShowCreateWorkspaceModal(true)}
                  disabled={loading}
                  className="sylvar-btn-secondary text-xs rounded-md px-2.5 py-1.5 transition-colors cursor-pointer"
                  title="Create new agency workspace"
                >
                  + New
                </button>
                {selectedWs && (
                  <button
                    onClick={() => {
                      const ws = workspaces.find((w) => w.workspace_id === selectedWs);
                      setRenameWorkspaceName(ws?.name || "");
                      setShowRenameWorkspaceModal(true);
                    }}
                    disabled={loading}
                    className="sylvar-btn-secondary text-xs rounded-md px-2.5 py-1.5 transition-colors cursor-pointer"
                    title="Rename selected workspace"
                  >
                    Rename
                  </button>
                )}
              </div>
            </div>

            {/* Client Brand Scoping */}
            <div>
              <span className="block text-xs font-medium text-[#9a928c] mb-1.5">
                Client Brand Space
              </span>
              <div className="flex items-center gap-2">
                <select
                  className="rounded-md border border-[#2d2833] bg-[#161518] px-3 py-1.5 text-xs font-medium text-[#f1eae4] focus:border-[#f59e0b] focus:outline-none transition-all"
                  value={selectedClient}
                  onChange={(e) => handleClientChange(e.target.value)}
                  aria-label="Client brand"
                >
                  {clients.length === 0 && (
                    <option value="">
                      {!selectedWs
                        ? "Select a workspace first"
                        : clientsStatus === "loading"
                        ? "Loading client brands…"
                        : clientsStatus === "error"
                        ? "Client brands failed to load"
                        : "No client brands provisioned"}
                    </option>
                  )}
                  {clients.map((c) => (
                    <option key={c.client_id} value={c.client_id}>
                      {c.name} ({c.code})
                    </option>
                  ))}
                </select>
                <button
                  onClick={() => setShowCreateClientModal(true)}
                  disabled={loading || !selectedWs}
                  className="sylvar-btn-secondary text-xs rounded-md px-2.5 py-1.5 transition-colors cursor-pointer"
                  title="Provision client brand space"
                >
                  + New
                </button>
                {selectedClient && (
                  <button
                    onClick={() => {
                      const cl = clients.find((c) => c.client_id === selectedClient);
                      setRenameClientName(cl?.name || "");
                      setShowRenameClientModal(true);
                    }}
                    disabled={loading}
                    className="sylvar-btn-secondary text-xs rounded-md px-2.5 py-1.5 transition-colors cursor-pointer"
                    title="Rename selected client brand"
                  >
                    Rename
                  </button>
                )}
              </div>
            </div>
          </div>

          {/* Right Status Actions & Memory Chip */}
          <div className="flex flex-wrap items-center gap-3 pt-2 lg:pt-0 border-t lg:border-t-0 border-[#232027]">
            <button
              onClick={() => setShowMemberModal(true)}
              disabled={!selectedWs}
              className="sylvar-btn-outline text-xs px-3 py-1.5 rounded-md font-medium transition-all cursor-pointer"
            >
              Team & Scoping
            </button>

            {/* Active Memory Chip */}
            <div className="flex items-center gap-2 bg-[#161518] border border-[#292530] rounded-md px-3 py-1.5 text-xs">
              <span className="text-[#8e847c] font-medium">Memory:</span>
              {memoryStatus === "error" ? (
                <span className="inline-flex items-center text-xs font-semibold bg-[#2a171a] text-[#fca5a5] px-2 py-0.5 rounded">
                  Load Error
                </span>
              ) : memoryStatus === "loading" ? (
                <span className="inline-flex items-center text-xs text-[#8e847c]">
                  Checking…
                </span>
              ) : activeSnapshotHash ? (
                <span className="inline-flex items-center gap-1.5 font-mono text-xs text-[#4ade80]">
                  <span className="h-1.5 w-1.5 rounded-full bg-[#4ade80]" />
                  {activeVersionTag ? `${activeVersionTag}` : "Active"} ({activeSnapshotHash.slice(0, 8)}…)
                </span>
              ) : (
                <span className="inline-flex items-center text-xs font-medium text-[#f59e0b]">
                  No Active Release
                </span>
              )}
            </div>
          </div>
        </div>
      </div>

      {activePipelineTab === "ALL" && (
        <section className="sylvar-overview-panel">
          <div className="sylvar-overview-kicker">GOVERNANCE SNAPSHOT</div>
          <div className="sylvar-overview-stats">
            <article><span>Active Memory</span><strong>{activeSnapshotHash ? (activeVersionTag || `v${activeVersionNumber ?? "—"}`) : "None"}</strong><small>{activeSnapshotHash ? "Verified brand knowledge active" : "Requires guideline approval"}</small></article>
            <article><span>Approved Rules</span><strong>{candidateSummary.approved}</strong><small>{candidateSummary.pending} pending candidate rules</small></article>
            <article><span>Open Reviews</span><strong>{reviews.filter((r) => r.status === "PENDING").length}</strong><small>{reviews.length} total review submissions</small></article>
            <article><span>Latest Audit Verdict</span><strong className={latestAudit?.overall_verdict === "PASS" ? "good" : latestAudit ? "warn" : ""}>{latestAudit?.overall_verdict || "—"}</strong><small>{latestAudit ? `${latestAudit.findings?.length ?? 0} findings in latest run` : "No audit executed"}</small></article>
          </div>
          <div className="sylvar-overview-grid">
            <div className="sylvar-overview-card">
              <h3>Active Brand Guidelines & Rules</h3>
              <p>Current knowledge base powering real-time terminology, color validation, and factual verification.</p>
              <div className="space-y-2.5 text-xs">
                <div className="flex justify-between py-1.5 border-b border-[#232027]">
                  <span className="text-[#8e847c]">Version Release</span>
                  <span className="font-mono text-[#f3ede7]">{activeVersionTag || "Unassigned"}</span>
                </div>
                <div className="flex justify-between py-1.5 border-b border-[#232027]">
                  <span className="text-[#8e847c]">Snapshot Integrity</span>
                  <span className="font-mono text-[#f3ede7]">{activeSnapshotHash ? `${activeSnapshotHash.slice(0, 16)}…` : "Not activated"}</span>
                </div>
                <div className="flex justify-between py-1.5 border-b border-[#232027]">
                  <span className="text-[#8e847c]">Rule Breakdown</span>
                  <span className="text-[#f3ede7]">{candidateSummary.approved} active / {candidateSummary.pending} staged</span>
                </div>
              </div>
              <div className="mt-4 pt-3 border-t border-[#232027] flex gap-2">
                <button
                  type="button"
                  onClick={() => setActivePipelineTab("MEMORY")}
                  className="sylvar-btn-primary text-xs px-3.5 py-1.5 rounded-md font-medium cursor-pointer"
                >
                  Manage Brand Memory
                </button>
              </div>
            </div>

            <div className="sylvar-overview-card">
              <div className="flex items-center justify-between mb-2">
                <h3>Governance Review Pipeline</h3>
                <span className="text-xs text-[#8e847c]">
                  {reviews.filter((r) => r.status === "PENDING").length} awaiting decision
                </span>
              </div>
              <p>Independent separation-of-duties review queue and cryptographic compliance certificates.</p>

              {reviews.length > 0 ? (
                <div className="border border-[#232027] rounded-md overflow-hidden text-xs">
                  <div className="grid grid-cols-12 bg-[#17161b] px-3 py-2 text-[#8e847c] font-medium border-b border-[#232027]">
                    <div className="col-span-4">Review ID</div>
                    <div className="col-span-4">Status</div>
                    <div className="col-span-4 text-right">Certificate</div>
                  </div>
                  <div className="divide-y divide-[#232027] max-h-48 overflow-y-auto">
                    {reviews.slice(0, 4).map((r) => (
                      <div key={r.review_id} className="grid grid-cols-12 px-3 py-2 items-center">
                        <div className="col-span-4 font-mono text-[#dfd4cc]">#{r.review_id.slice(0, 8)}</div>
                        <div className="col-span-4">
                          <span className={`text-[10px] px-2 py-0.5 rounded font-semibold ${
                            r.status === "APPROVED"
                              ? "bg-[#14281a] text-[#4ade80] border border-[#234e30]"
                              : r.status === "REJECTED"
                              ? "bg-[#2d1618] text-[#f87171] border border-[#5a2327]"
                              : "bg-[#292015] text-[#fbbf24] border border-[#4d381c]"
                          }`}>
                            {r.status}
                          </span>
                        </div>
                        <div className="col-span-4 text-right font-mono text-[11px] text-[#8e847c]">
                          {r.certificate ? "✓ Issued" : "—"}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="border border-[#232027] rounded-md p-4 text-center text-xs text-[#8e847c] bg-[#161519]">
                  No review requests submitted yet for this client space.
                </div>
              )}

              <div className="mt-4 pt-3 border-t border-[#232027] flex gap-2">
                <button
                  type="button"
                  onClick={() => setActivePipelineTab("AUDIT")}
                  className="sylvar-btn-outline text-xs px-3 py-1.5 rounded-md font-medium cursor-pointer"
                >
                  Create & Audit Content
                </button>
                <button
                  type="button"
                  onClick={() => setActivePipelineTab("GOVERNANCE")}
                  className="sylvar-btn-secondary text-xs px-3 py-1.5 rounded-md font-medium cursor-pointer"
                >
                  View Review Queue
                </button>
              </div>
            </div>
          </div>
        </section>
      )}

      {/* STAGE 1: LIVING BRAND MEMORY & GUIDELINE INGESTION */}
      {activePipelineTab === "MEMORY" && (
        <section className="bg-[#131215] rounded-lg border border-[#232027] p-5 space-y-5">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-[#232027] pb-4">
            <div>
              <h2 className="text-base font-semibold text-[#f7f1eb]">
                Living Brand Memory & Guideline Ingestion
              </h2>
              <p className="text-xs text-[#8e827a] mt-0.5">
                Ingest guideline documents (PDF, DOCX, Markdown, TXT) and extract structured rules across Terminology, Color, and Facts.
              </p>
            </div>
            <span className="self-start sm:self-auto inline-flex items-center px-2.5 py-1 rounded text-xs font-medium bg-[#1e1b26] text-[#c4b5fd] border border-[#372f48]">
              Brand Manager Role
            </span>
          </div>

          {/* Guideline File Upload Dropzone */}
          <div className="bg-[#161519] border border-[#232027] rounded-md p-4 space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <label
                  htmlFor="guideline-file"
                  className="inline-flex items-center gap-2 px-3 py-1.5 rounded-md border border-[#342f3c] bg-[#1a1820] text-xs font-medium text-[#eee8e2] hover:bg-[#23202a] transition-all cursor-pointer"
                >
                  <svg className="w-3.5 h-3.5 text-[#f59e0b]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                  </svg>
                  Choose Guideline File
                </label>
                <input
                  id="guideline-file"
                  key={fileInputKey}
                  type="file"
                  accept={GUIDELINE_ACCEPT}
                  onChange={handleFileSelected}
                  disabled={loading || isExtracting || uploadBlockReason !== null}
                  className="sr-only"
                />
                <span className="text-xs text-[#8a7f77] hidden sm:inline">
                  .txt, .md, .docx, .pdf (Max 10MB)
                </span>
              </div>

              {isExtracting && (
                <div className="inline-flex items-center gap-2 text-xs text-[#f59e0b] bg-[#221c14] border border-[#44331e] px-3 py-1 rounded-md">
                  <span>Extracting candidate rules via Gemini…</span>
                </div>
              )}
            </div>

            {/* Block reason notes & validation feedback */}
            {uploadBlockReason && (
              <p role="note" className="text-xs text-[#fcd34d] bg-[#201a14] border border-[#4d381c] rounded-md px-3 py-2">
                {uploadBlockReason}
              </p>
            )}

            {selectedFile && (
              <div className="flex items-center justify-between bg-[#191822] border border-[#302b3d] rounded-md px-3 py-2 text-xs text-[#e4def0]">
                <div className="flex items-center gap-2 truncate">
                  <span className="font-medium text-[#9a90b0]">Selected:</span>
                  <span className="font-mono truncate">{selectedFile.name}</span>
                  <span className="text-[#8e84a8] text-[11px]">({formatFileSize(selectedFile.size)})</span>
                </div>
                <button
                  onClick={clearSelectedFile}
                  disabled={loading}
                  className="text-xs font-medium text-[#c4b5fd] hover:text-[#e4def0] cursor-pointer ml-3 shrink-0"
                >
                  Clear
                </button>
              </div>
            )}

            {fileError && (
              <div role="alert" className="text-xs text-[#fca5a5] bg-[#241719] border border-[#522b31] rounded-md px-3 py-2 font-medium">
                {fileError}
              </div>
            )}

            <div>
              <span className="block text-xs font-medium text-[#9a928c] mb-1.5">
                Or Paste Guideline Text
              </span>
              <textarea
                rows={3}
                value={guidelineText}
                onChange={(e) => setGuidelineText(e.target.value)}
                className="w-full rounded-md border border-[#332d3a] p-3 font-mono text-xs text-[#f1eae4] bg-[#141316] focus:border-[#f59e0b] focus:outline-none transition-all"
                placeholder="Paste brand guideline rules, forbidden claims, or style requirements..."
              />
            </div>
          </div>

          {/* Extracted Candidates Drawer */}
          {candidates.length > 0 && (
            <div className="border border-[#232027] rounded-md bg-[#161519] overflow-hidden">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 px-4 py-3 bg-[#19181d] border-b border-[#232027]">
                <span className="text-xs font-semibold text-[#f1eae4]">
                  Extracted Candidate Rules ({candidateSummary.total} Total)
                </span>
                <div className="flex items-center gap-2 text-xs font-medium">
                  <span className="bg-[#14281a] text-[#4ade80] border border-[#234e30] px-2 py-0.5 rounded">
                    {candidateSummary.approved} Approved
                  </span>
                  <span className="bg-[#292015] text-[#fbbf24] border border-[#4d381c] px-2 py-0.5 rounded">
                    {candidateSummary.pending} Pending
                  </span>
                  {candidateSummary.rejected > 0 && (
                    <span className="bg-[#2d1618] text-[#f87171] border border-[#5a2327] px-2 py-0.5 rounded">
                      {candidateSummary.rejected} Rejected
                    </span>
                  )}
                </div>
              </div>

              <div className="divide-y divide-[#232027] max-h-64 overflow-y-auto">
                {candidates.map((cand) => {
                  const bucket = classifyCandidate(cand.review_status);
                  const badge =
                    bucket === "approved"
                      ? "bg-[#14281a] text-[#4ade80] border-[#234e30]"
                      : bucket === "pending"
                      ? "bg-[#292015] text-[#fbbf24] border-[#4d381c]"
                      : bucket === "rejected"
                      ? "bg-[#2d1618] text-[#f87171] border-[#5a2327]"
                      : "bg-[#201e25] text-[#d4cbdc] border-[#383344]";

                  return (
                    <div
                      key={cand.candidate_id}
                      className="p-3 text-xs flex justify-between items-start gap-3 hover:bg-[#19181d] transition-all"
                    >
                      <div className="space-y-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-xs text-[#f59e0b] bg-[#221c14] border border-[#44331e] px-1.5 py-0.5 rounded">
                            {cand.category}
                          </span>
                        </div>
                        <p className="font-mono text-xs text-[#c9bfb5] bg-[#141316] border border-[#26232b] rounded p-2 overflow-x-auto">
                          {JSON.stringify(cand.payload)}
                        </p>
                      </div>
                      <span className={`text-xs px-2 py-0.5 rounded font-medium border shrink-0 ${badge}`}>
                        {cand.review_status}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Action Trigger Buttons */}
          <div className="flex flex-wrap items-center gap-3 pt-2">
            <button
              onClick={() => void handleUploadAndExtract()}
              disabled={loading || isExtracting || uploadBlockReason !== null}
              className="sylvar-btn-primary inline-flex items-center gap-2 text-xs font-semibold px-4 py-2 rounded-md cursor-pointer disabled:opacity-40"
            >
              {isExtracting
                ? "Extracting Candidate Rules…"
                : selectedFile
                ? `Upload '${selectedFile.name}' & Extract Rules`
                : "Extract Rules from Pasted Text"}
            </button>

            <button
              onClick={() => void handleApproveAndActivate()}
              disabled={loading || activationBlockReason !== null}
              className="sylvar-btn-success inline-flex items-center gap-2 text-xs font-semibold px-4 py-2 rounded-md cursor-pointer disabled:opacity-40"
            >
              {candidateSummary.pending > 0
                ? `Approve & Activate Memory Release (${candidateSummary.pending} Pending Rules)`
                : candidateSummary.approved > 0
                ? `Publish Memory Release (${candidateSummary.approved} Approved Rules)`
                : "Approve & Activate Memory Release (0 Staged Candidates)"}
            </button>
          </div>

          {activationBlockReason && memoryStatus === "error" && (
            <p role="note" className="text-xs text-rose-800 bg-rose-50 border border-rose-200 rounded-xl px-3 py-2 font-medium">
              {activationBlockReason}
            </p>
          )}
        </section>
      )}

      {/* STAGE 2: CONTENT GOVERNANCE STUDIO & MULTI-TIER AUDIT */}
      {activePipelineTab === "AUDIT" && (
        <section className="bg-[#131215] rounded-lg border border-[#232027] p-5 space-y-5">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-[#232027] pb-4">
            <div>
              <h2 className="text-base font-semibold text-[#f7f1eb]">
                Content Governance Studio & Pre-Publication CI/CD
              </h2>
              <p className="text-xs text-[#8e827a] mt-0.5">
                Draft content assets, execute real-time multi-tier brand verification, and inspect intent-preserving surgical remediation proposals.
              </p>
            </div>
            <span className="self-start sm:self-auto inline-flex items-center px-2.5 py-1 rounded text-xs font-medium bg-[#161b24] text-[#93c5fd] border border-[#24354a]">
              Content Creator Role (Version {currentVersionNumber})
            </span>
          </div>

          {/* Informative banner when auditing is disabled */}
          {memoryStatus === "error" && (
            <div role="alert" className="bg-[#241719] border border-[#522b31] text-[#fca5a5] text-xs px-3.5 py-2.5 rounded-md font-medium">
              <span className="font-bold">Auditing unavailable:</span> The active brand memory could not be read.
            </div>
          )}
          {memoryStatus !== "error" && !activeSnapshotHash && (
            <div className="bg-[#201a14] border border-[#4d381c] text-[#fcd34d] text-xs px-3.5 py-2.5 rounded-md flex items-center gap-2">
              <span className="font-bold">Auditing Disabled:</span>
              <span>
                No Living Brand Memory snapshot is active. A Brand Manager must ingest guidelines and activate a memory snapshot in Stage 1 first.
              </span>
            </div>
          )}

          {/* Content Format / Channel Selector Pills */}
          <div className="space-y-1.5">
            <span className="block text-xs font-medium text-[#9a928c]">
              Content Format / Channel Template
            </span>
            <div className="flex items-center gap-2 flex-wrap">
              {(
                [
                  { key: "SOCIAL_MEDIA", label: "Social Media" },
                  { key: "ADVERTISEMENT", label: "Advertisement" },
                  { key: "BLOG", label: "Blog Post" },
                  { key: "EMAIL", label: "Email Newsletter" },
                ] as const
              ).map((fmt) => (
                <button
                  key={fmt.key}
                  type="button"
                  onClick={() => handleFormatChange(fmt.key)}
                  className={`text-xs font-medium px-3 py-1.5 rounded-md border transition-all cursor-pointer ${
                    contentFormat === fmt.key
                      ? "bg-[#272118] text-[#f59e0b] border-[#553f1c]"
                      : "bg-[#161518] text-[#8e847c] border-[#2b2733] hover:text-[#eee8e2] hover:bg-[#1f1d24]"
                  }`}
                >
                  {fmt.label}
                </button>
              ))}
            </div>
          </div>

          {/* Draft Inputs */}
          <div className="space-y-3">
            <div>
              <label className="block text-xs font-medium text-[#9a928c] mb-1.5">
                Asset Title
              </label>
              <input
                type="text"
                value={contentTitle}
                onChange={(e) => setContentTitle(e.target.value)}
                className="w-full rounded-md border border-[#332d3a] px-3.5 py-2 text-xs font-medium text-[#f1eae4] bg-[#141316] focus:border-[#f59e0b] focus:outline-none transition-all"
                placeholder="e.g. Spring Serum Launch Copy"
              />
            </div>
            <div>
              <div className="flex justify-between items-center mb-1.5">
                <label className="block text-xs font-medium text-[#9a928c]">
                  Draft Content
                </label>
                <span className="text-xs text-[#8a7f77]">
                  {contentText.length} characters | {contentText.split(/\s+/).filter(Boolean).length} words
                </span>
              </div>
              <textarea
                rows={3}
                value={contentText}
                onChange={(e) => setContentText(e.target.value)}
                className="w-full rounded-md border border-[#332d3a] p-3 text-xs text-[#f1eae4] bg-[#141316] focus:border-[#f59e0b] focus:outline-none transition-all font-sans"
              />
            </div>
          </div>

          {/* Action Row */}
          <div className="flex flex-wrap items-center gap-2.5">
            <button
              onClick={() => void handleRunAudit()}
              disabled={loading || !activeSnapshotHash}
              title={!activeSnapshotHash ? "Activate a memory release in Stage 1 first" : "Audit content against brand memory"}
              className="sylvar-btn-primary text-xs font-semibold px-4 py-2 rounded-md cursor-pointer disabled:opacity-40"
            >
              Run Pre-Publication Audit
            </button>
            <button
              onClick={() => handleLoadDraft("non-compliant")}
              className="sylvar-btn-outline text-xs px-3.5 py-2 rounded-md font-medium transition-all cursor-pointer"
            >
              Load Non-Compliant Draft
            </button>
            <button
              onClick={() => handleLoadDraft("compliant")}
              className="sylvar-btn-outline text-xs px-3.5 py-2 rounded-md font-medium transition-all cursor-pointer"
            >
              Load Compliant Draft
            </button>
          </div>

          {/* Live Diagnostic Scorecard & Surgical Diff Proposals */}
          {latestAudit && (() => {
            const findings = latestAudit.findings || [];
            return (
              <div className="mt-4 border border-[#232027] rounded-md p-4 bg-[#161519] space-y-4">
                <div className="flex items-center justify-between border-b border-[#232027] pb-3">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-xs text-[#f1eae4]">Diagnostic Scorecard:</span>
                    <span className="font-mono text-xs text-[#8e847c]">Run #{latestAudit.audit_run_id.slice(0, 8)}</span>
                  </div>
                  <span
                    className={`px-2.5 py-1 rounded text-xs font-semibold ${
                      latestAudit.overall_verdict === "BLOCKED"
                        ? "bg-[#2d1618] text-[#f87171] border border-[#5a2327]"
                        : latestAudit.overall_verdict === "WARNINGS"
                        ? "bg-[#292015] text-[#fbbf24] border border-[#4d381c]"
                        : "bg-[#14281a] text-[#4ade80] border border-[#234e30]"
                    }`}
                  >
                    {latestAudit.overall_verdict}
                  </span>
                </div>

                {/* 3-Tier Multi-Engine Breakdown */}
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
                  {latestAudit.checks.map((c) => (
                    <div key={c.check_id} className="bg-[#131215] border border-[#232027] rounded-md p-3">
                      <div className="text-xs text-[#8e847c] font-medium">{c.engine_type}</div>
                      <div className="font-semibold text-sm mt-0.5 text-[#f1eae4]">{c.status}</div>
                      <div className="text-[11px] text-[#716862] mt-0.5">{c.execution_time_ms}ms execution</div>
                    </div>
                  ))}
                </div>

                {/* Governance Findings & Intent-Preserving Diff View */}
                {findings.length > 0 ? (
                  <div className="space-y-3 pt-1">
                    <span className="text-xs font-semibold text-[#f1eae4] block">
                      Governance Findings & Surgical Corrections ({findings.length}):
                    </span>
                    {findings.map((f) => (
                      <div
                        key={f.finding_id}
                        className={`bg-[#131215] border border-[#232027] rounded-md p-3.5 text-xs space-y-2.5 border-l-2 ${
                          f.severity === "CRITICAL"
                            ? "border-l-rose-500"
                            : f.severity === "MAJOR"
                            ? "border-l-amber-500"
                            : "border-l-indigo-400"
                        }`}
                      >
                        <div className="flex justify-between items-center">
                          <div className="flex items-center gap-2">
                            <span className="font-mono text-[#e5ded7] font-semibold bg-[#1a1820] border border-[#2d2838] px-2 py-0.5 rounded text-xs">
                              {f.rule_code}
                            </span>
                            {f.evidence?.verdict === "UNVERIFIED" && (
                              <span className="bg-[#20182a] text-[#c4b5fd] border border-[#3d2c52] px-2 py-0.5 rounded text-xs font-medium">
                                UNVERIFIED CLAIM
                              </span>
                            )}
                          </div>
                          <span
                            className={`px-2 py-0.5 rounded font-medium text-xs border ${
                              f.severity === "CRITICAL"
                                ? "bg-[#2d1618] text-[#f87171] border-[#5a2327]"
                                : "bg-[#292015] text-[#fbbf24] border-[#4d381c]"
                            }`}
                          >
                            {f.severity}
                          </span>
                        </div>
                        <p className="text-[#eee8e2] text-xs leading-relaxed">{f.message}</p>
                        {f.snippet && (
                          <div className="p-2 bg-[#17161a] font-mono text-[#c4b9b0] rounded text-xs border border-[#26232c]">
                            Context Snippet: &ldquo;{f.snippet}&rdquo;
                          </div>
                        )}

                        {/* Intent-Preserving Rewriter Diff Proposals */}
                        {(f.suggestions || []).map((s) => (
                          <div
                            key={s.suggestion_id}
                            className="bg-[#151916] border border-[#25422e] rounded-md p-3 space-y-2"
                          >
                            <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
                              <div className="space-y-1.5 flex-1 min-w-0">
                                <span className="text-[#4ade80] font-semibold block text-xs">
                                  Surgical Correction Proposal (Intent-Preserving)
                                </span>
                                {/* Visual Diff Comparison */}
                                <div className="text-xs font-mono bg-[#111412] border border-[#233f2c] rounded p-2.5 space-y-1">
                                  <div>
                                    <span className="text-rose-400 font-semibold mr-2">- Original:</span>
                                    <span className="line-through bg-[#2d1618] text-[#fca5a5] px-1.5 py-0.5 rounded">
                                      {s.original_text}
                                    </span>
                                  </div>
                                  <div>
                                    <span className="text-emerald-400 font-semibold mr-2">+ Proposed:</span>
                                    <span className="bg-[#14281a] text-[#86efac] font-semibold px-1.5 py-0.5 rounded">
                                      {s.suggested_text}
                                    </span>
                                  </div>
                                </div>
                                <p className="text-[#8e847c] text-xs italic">
                                  Guideline Rationale: {s.rationale}
                                </p>
                              </div>
                              <button
                                onClick={() => void handleApplyRemediation(s.suggestion_id)}
                                className="sylvar-btn-success text-xs font-semibold px-3 py-1.5 rounded-md transition-all shrink-0 cursor-pointer"
                              >
                                Apply Surgical Fix
                              </button>
                            </div>
                          </div>
                        ))}
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="p-3 bg-[#14281a] border border-[#234e30] rounded-md text-xs text-[#4ade80] font-medium flex items-center gap-2">
                    <span>✓</span>
                    <span>0 compliance violations detected. Content matches approved brand memory.</span>
                  </div>
                )}

                {/* Submit to Review Action */}
                <div className="pt-3 border-t border-[#232027] flex justify-end">
                  <button
                    onClick={() => void handleSubmitReview()}
                    disabled={latestAudit.overall_verdict === "BLOCKED" || loading}
                    className="sylvar-btn-primary text-xs font-semibold px-4 py-2 rounded-md disabled:opacity-40 transition-all cursor-pointer"
                  >
                    Submit Clean Version for Brand Manager Approval
                  </button>
                </div>
              </div>
            );
          })()}
        </section>
      )}

      {/* STAGE 3: BRAND MANAGER REVIEW QUEUE & VERIFIABLE CERTIFICATES */}
      {activePipelineTab === "GOVERNANCE" && (
        <section className="bg-[#131215] rounded-lg border border-[#232027] p-5 space-y-5">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-[#232027] pb-4">
            <div>
              <h2 className="text-base font-semibold text-[#f7f1eb]">
                Brand Manager Review Queue & Compliance Certificates
              </h2>
              <p className="text-xs text-[#8e827a] mt-0.5">
                Evaluate submitted assets, enforce Separation of Duties (ADR-004), and issue cryptographic compliance certificates.
              </p>
            </div>
            <span className="self-start sm:self-auto inline-flex items-center px-2.5 py-1 rounded text-xs font-medium bg-[#1e1b26] text-[#c4b5fd] border border-[#372f48]">
              Brand Manager Role
            </span>
          </div>

          {/* Separation of Duties (ADR-004) Card */}
          <div className="bg-[#17151e] border border-[#2f273d] text-[#e2dcee] text-xs p-3.5 rounded-md space-y-1">
            <div className="font-semibold flex items-center gap-2 text-[#c4b5fd]">
              <span>Separation of Duties Policy (ADR-004)</span>
            </div>
            <p className="text-[#a499b8] leading-relaxed">
              Content Creators cannot approve their own submissions. An independent Brand Manager must review the Diagnostic Scorecard, evaluate advisory findings, and issue the immutable cryptographic Compliance Certificate.
            </p>
          </div>

          {/* Review Request Queue */}
          {reviews.length > 0 ? (
            <div className="space-y-3">
              {reviews.map((r) => {
                const isSubmitter = Boolean(userProfile?.user_id && r.submitted_by_user_id === userProfile.user_id);
                const canApprove = isBrandManager && !isSubmitter;

                return (
                  <div key={r.review_id} className="border border-[#232027] rounded-md p-4 bg-[#161519] space-y-3">
                    <div className="flex justify-between items-center">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-xs text-[#f1eae4]">Review Request #{r.review_id.slice(0, 8)}</span>
                        {r.created_at && (
                          <span className="text-xs text-[#8e847c]">
                            {new Date(r.created_at).toLocaleTimeString()}
                          </span>
                        )}
                      </div>
                      <span
                        className={`text-xs px-2.5 py-0.5 rounded font-semibold border ${
                          r.status === "APPROVED"
                            ? "bg-[#14281a] text-[#4ade80] border-[#234e30]"
                            : r.status === "REJECTED"
                            ? "bg-[#2d1618] text-[#f87171] border-[#5a2327]"
                            : r.status === "CHANGES_REQUESTED"
                            ? "bg-[#292015] text-[#fbbf24] border-[#4d381c]"
                            : "bg-[#161f2c] text-[#93c5fd] border-[#26374e]"
                        }`}
                      >
                        {r.status}
                      </span>
                    </div>

                    {r.decision_notes && (
                      <div className="text-xs bg-[#131215] border border-[#232027] rounded-md p-3 text-[#dfd4cc] space-y-1">
                        <span className="font-semibold text-[#f1eae4]">Reviewer Notes: </span>
                        <span>{r.decision_notes}</span>
                      </div>
                    )}

                    {r.status === "PENDING" && (
                      <div className="pt-2 border-t border-[#232027] space-y-2">
                        {!isBrandManager && (
                          <div className="text-xs text-[#fcd34d] bg-[#201a14] border border-[#4d381c] px-3 py-1.5 rounded-md font-medium">
                            Approval restricted to Brand Managers (Separation of Duties). Your current client assignment is &lsquo;{currentClientRole}&rsquo;.
                          </div>
                        )}
                        {isSubmitter && isBrandManager && (
                          <div className="text-xs text-[#fcd34d] bg-[#201a14] border border-[#4d381c] px-3 py-1.5 rounded-md font-medium">
                            Submitter cannot self-approve (Separation of Duties). Requires review by another Brand Manager.
                          </div>
                        )}
                        <div className="flex gap-2 flex-wrap">
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
                            className="sylvar-btn-success text-xs font-semibold px-3.5 py-1.5 rounded-md disabled:opacity-40 transition-all cursor-pointer"
                          >
                            Approve & Issue Certificate
                          </button>
                          <button
                            onClick={() => handleRequestChangesReview(r.review_id)}
                            disabled={loading || !isBrandManager}
                            className="sylvar-btn-primary text-xs font-semibold px-3.5 py-1.5 rounded-md disabled:opacity-40 transition-all cursor-pointer"
                          >
                            Request Changes
                          </button>
                          <button
                            onClick={() => handleRejectReview(r.review_id)}
                            disabled={loading || !isBrandManager}
                            className="sylvar-btn-danger text-xs font-semibold px-3.5 py-1.5 rounded-md disabled:opacity-40 transition-all cursor-pointer"
                          >
                            Reject
                          </button>
                        </div>
                      </div>
                    )}

                    {/* Verifiable Cryptographic Compliance Certificate */}
                    {r.certificate && (() => {
                      const payload = r.certificate.certificate_payload || {};
                      const isDemoOnly = Boolean(payload.is_demo_only || payload.certificate_type === "DEMO_COMPLIANCE_CERTIFICATE");

                      return (
                        <div
                          className={`mt-3 bg-[#131715] border rounded-md p-4 text-xs space-y-3 ${
                            isDemoOnly ? "border-[#544322]" : "border-[#234e30]"
                          }`}
                        >
                          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-[#233e2c] pb-2">
                            <span className={`font-semibold tracking-tight ${isDemoOnly ? "text-[#fcd34d]" : "text-[#4ade80]"}`}>
                              {isDemoOnly ? "DEMO COMPLIANCE CERTIFICATE (UNVERIFIED HEURISTIC AUDIT)" : "✓ VERIFIED COMPLIANCE CERTIFICATE"}
                            </span>
                            <button
                              onClick={() => downloadCertificate(r.certificate!)}
                              className="sylvar-btn-outline text-xs px-3 py-1 rounded-md font-medium cursor-pointer self-start sm:self-auto"
                            >
                              Export Certificate JSON
                            </button>
                          </div>

                          {isDemoOnly && Array.isArray(payload.disclosures) && payload.disclosures.length > 0 && (
                            <div className="p-3 bg-[#201a14] text-[#fcd34d] border border-[#4d381c] rounded-md text-xs space-y-1">
                              <span className="font-semibold">Required Regulatory Disclosures:</span>
                              {payload.disclosures.map((d: string, i: number) => (
                                <p key={i}>• {d}</p>
                              ))}
                            </div>
                          )}

                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs font-mono text-[#a89d93]">
                            <div className="bg-[#161a17] border border-[#233527] rounded p-2 truncate">
                              <span className="font-semibold text-[#eee8e2] block">Certificate ID:</span>
                              {r.certificate.certificate_id}
                            </div>
                            <div className="bg-[#161a17] border border-[#233527] rounded p-2 truncate">
                              <span className="font-semibold text-[#eee8e2] block">Certificate SHA-256:</span>
                              {r.certificate.certificate_hash}
                            </div>
                            <div className="bg-[#161a17] border border-[#233527] rounded p-2 truncate">
                              <span className="font-semibold text-[#eee8e2] block">Snapshot SHA-256:</span>
                              {r.certificate.snapshot_hash}
                            </div>
                            <div className="bg-[#161a17] border border-[#233527] rounded p-2 truncate">
                              <span className="font-semibold text-[#eee8e2] block">Approved At:</span>
                              {new Date(r.certificate.issued_at).toLocaleString()}
                            </div>
                          </div>
                        </div>
                      );
                    })()}
                  </div>
                );
              })}
            </div>
          ) : (
            <p className="text-xs text-[#8e847c] italic py-2">No approval requests in the review queue.</p>
          )}
        </section>
      )}

      {/* MODAL: CREATE WORKSPACE */}
      {showCreateWorkspaceModal && (
        <div className="fixed inset-0 bg-[#060608]/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-[#141317] rounded-lg shadow-elevated border border-[#2b2734] max-w-sm w-full p-6 space-y-4">
            <h3 className="text-base font-semibold text-[#f7f1eb]">Create Agency Workspace</h3>
            <p className="text-xs text-[#8e827a]">
              Create a high-level tenant partition for agency workspaces and client brand groups.
            </p>
            <form onSubmit={handleCreateWorkspaceSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-[#9a928c] mb-1.5">
                  Workspace Name
                </label>
                <input
                  type="text"
                  value={newWorkspaceName}
                  onChange={(e) => setNewWorkspaceName(e.target.value)}
                  className="w-full rounded-md border border-[#332d3a] px-3.5 py-2 text-xs text-[#f1eae4] bg-[#100f13] focus:border-[#f59e0b] focus:outline-none"
                  placeholder="e.g. Apex Media Agency"
                  autoFocus
                />
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowCreateWorkspaceModal(false)}
                  className="sylvar-btn-secondary text-xs px-3.5 py-2 rounded-md font-medium cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={loading || !newWorkspaceName.trim()}
                  className="sylvar-btn-primary text-xs font-semibold px-4 py-2 rounded-md disabled:opacity-50 transition-all cursor-pointer shadow-sm"
                >
                  {loading ? "Creating…" : "Create Workspace"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL: RENAME WORKSPACE */}
      {showRenameWorkspaceModal && (
        <div className="fixed inset-0 bg-[#060608]/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-[#141317] rounded-lg shadow-elevated border border-[#2b2734] max-w-sm w-full p-6 space-y-4">
            <h3 className="text-base font-semibold text-[#f7f1eb]">Rename Workspace</h3>
            <p className="text-xs text-[#8e827a]">
              Update the display name of your agency workspace.
            </p>
            <form onSubmit={handleRenameWorkspaceSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-[#9a928c] mb-1.5">
                  New Workspace Name
                </label>
                <input
                  type="text"
                  value={renameWorkspaceName}
                  onChange={(e) => setRenameWorkspaceName(e.target.value)}
                  className="w-full rounded-md border border-[#332d3a] px-3.5 py-2 text-xs text-[#f1eae4] bg-[#100f13] focus:border-[#f59e0b] focus:outline-none"
                  placeholder="e.g. Acme Global Studio"
                  autoFocus
                />
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowRenameWorkspaceModal(false)}
                  className="sylvar-btn-secondary text-xs px-3.5 py-2 rounded-md font-medium cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={loading || !renameWorkspaceName.trim()}
                  className="sylvar-btn-primary text-xs font-semibold px-4 py-2 rounded-md disabled:opacity-50 transition-all cursor-pointer shadow-sm"
                >
                  {loading ? "Renaming…" : "Save Workspace Name"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL: PROVISION CLIENT BRAND */}
      {showCreateClientModal && (
        <div className="fixed inset-0 bg-[#060608]/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-[#141317] rounded-lg shadow-elevated border border-[#2b2734] max-w-sm w-full p-6 space-y-4">
            <h3 className="text-base font-semibold text-[#f7f1eb]">Provision Client Brand Space</h3>
            <p className="text-xs text-[#8e827a]">
              Provisions a dedicated client brand workspace and atomically assigns you the initial BRAND_MANAGER role (ADR-003).
            </p>
            <div className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-[#9a928c] mb-1.5">
                  Client Brand Name
                </label>
                <input
                  type="text"
                  value={newClientName}
                  onChange={(e) => setNewClientName(e.target.value)}
                  className="w-full rounded-md border border-[#332d3a] px-3.5 py-2 text-xs text-[#f1eae4] bg-[#100f13] focus:border-[#f59e0b] focus:outline-none"
                  placeholder="e.g. Verve Botanicals"
                  autoFocus
                />
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowCreateClientModal(false)}
                  className="sylvar-btn-secondary text-xs px-3.5 py-2 rounded-md font-medium cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={() => void handleCreateClient()}
                  disabled={loading || !newClientName.trim()}
                  className="sylvar-btn-primary text-xs font-semibold px-4 py-2 rounded-md disabled:opacity-50 transition-all cursor-pointer shadow-sm"
                >
                  {loading ? "Creating…" : "Create Client Brand"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* MODAL: RENAME CLIENT BRAND */}
      {showRenameClientModal && (
        <div className="fixed inset-0 bg-[#060608]/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-[#141317] rounded-lg shadow-elevated border border-[#2b2734] max-w-sm w-full p-6 space-y-4">
            <h3 className="text-base font-semibold text-[#f7f1eb]">Rename Client Brand</h3>
            <p className="text-xs text-[#8e827a]">
              Update the official display name of the selected client brand space.
            </p>
            <div className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-[#9a928c] mb-1.5">
                  New Client Brand Name
                </label>
                <input
                  type="text"
                  value={renameClientName}
                  onChange={(e) => setRenameClientName(e.target.value)}
                  className="w-full rounded-md border border-[#332d3a] px-3.5 py-2 text-xs text-[#f1eae4] bg-[#100f13] focus:border-[#f59e0b] focus:outline-none"
                  placeholder="e.g. Verve Organics"
                  autoFocus
                />
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowRenameClientModal(false)}
                  className="sylvar-btn-secondary text-xs px-3.5 py-2 rounded-md font-medium cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={() => void handleRenameClientSubmit()}
                  disabled={loading || !renameClientName.trim()}
                  className="sylvar-btn-primary text-xs font-semibold px-4 py-2 rounded-md disabled:opacity-50 transition-all cursor-pointer shadow-sm"
                >
                  {loading ? "Saving…" : "Save Brand Name"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* MODAL: TEAM & SCOPING */}
      {showMemberModal && (
        <div className="fixed inset-0 bg-[#060608]/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-[#141317] rounded-lg shadow-elevated border border-[#2b2734] max-w-md w-full p-6 space-y-4">
            <div className="flex justify-between items-center border-b border-[#232027] pb-3">
              <h3 className="text-base font-semibold text-[#f7f1eb]">
                Team Scoping & Membership (ADR-003)
              </h3>
              <button
                onClick={() => setShowMemberModal(false)}
                className="text-[#8e827a] hover:text-[#f7f1eb] text-lg leading-none cursor-pointer"
              >
                ×
              </button>
            </div>
            {userProfile && (
              <p className="text-xs text-[#8e847c]">
                Authenticated user: <span className="font-mono font-medium text-[#f7f1eb]">{userProfile.email}</span>
              </p>
            )}
            <div className="space-y-3">
              <div>
                <label className="block text-xs font-medium text-[#9a928c] mb-1.5">
                  Member Email
                </label>
                <input
                  type="email"
                  placeholder="member@agency.com"
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                  className="w-full rounded-md border border-[#332d3a] px-3.5 py-2 text-xs text-[#f1eae4] bg-[#100f13] focus:border-[#f59e0b] focus:outline-none"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-[#9a928c] mb-1.5">
                  Role Assignment
                </label>
                <select
                  value={inviteRole}
                  onChange={(e) => setInviteRole(e.target.value)}
                  className="w-full rounded-md border border-[#332d3a] px-3.5 py-2 text-xs text-[#f1eae4] bg-[#100f13] focus:border-[#f59e0b] focus:outline-none"
                >
                  <option value="CONTENT_CREATOR">CONTENT_CREATOR</option>
                  <option value="BRAND_MANAGER">BRAND_MANAGER</option>
                  <option value="WORKSPACE_ADMIN">WORKSPACE_ADMIN</option>
                </select>
              </div>
              <div className="flex justify-end gap-2 pt-2 border-t border-[#232027]">
                <button
                  type="button"
                  onClick={() => setShowMemberModal(false)}
                  className="sylvar-btn-secondary text-xs px-3.5 py-2 rounded-md font-medium cursor-pointer"
                >
                  Close
                </button>
                <button
                  type="button"
                  onClick={() => void handleInviteMember()}
                  disabled={loading || !inviteEmail.trim()}
                  className="sylvar-btn-primary text-xs font-semibold px-4 py-2 rounded-md disabled:opacity-50 transition-all cursor-pointer shadow-sm"
                >
                  Invite Member
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* MODAL: MANDATORY REVIEW ACTION COMMENTS (Batch 3 Feature B) */}
      {reviewAction && (
        <div className="fixed inset-0 bg-[#060608]/80 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-[#141317] rounded-lg shadow-elevated border border-[#2b2734] max-w-md w-full p-6 space-y-4">
            <div className="flex justify-between items-center border-b border-[#232027] pb-3">
              <h3 className="font-semibold text-base text-[#f7f1eb]">
                {reviewAction.action === "REJECT" ? "Reject Submission" : "Request Content Changes"}
              </h3>
              <button
                type="button"
                onClick={() => setReviewAction(null)}
                className="text-[#8e827a] hover:text-[#f7f1eb] text-lg leading-none cursor-pointer"
              >
                ×
              </button>
            </div>
            <p className="text-xs text-[#8e827a]">
              Reviewer comments are mandatory to record actionable audit feedback in the permanent governance log.
            </p>
            {reviewActionError && (
              <div className="text-xs text-[#fca5a5] bg-[#241719] border border-[#522b31] p-3 rounded-md font-medium">
                {reviewActionError}
              </div>
            )}
            <textarea
              rows={3}
              value={reviewActionNotes}
              onChange={(e) => setReviewActionNotes(e.target.value)}
              placeholder="Enter detailed reviewer feedback and required changes..."
              className="w-full rounded-md border border-[#332d3a] p-3 text-xs text-[#f1eae4] bg-[#100f13] focus:border-[#f59e0b] focus:outline-none"
            />
            <div className="flex justify-end gap-2 pt-2 border-t border-[#232027]">
              <button
                type="button"
                onClick={() => setReviewAction(null)}
                className="sylvar-btn-secondary text-xs px-3.5 py-2 rounded-md font-medium cursor-pointer"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => void submitReviewAction()}
                disabled={loading || !reviewActionNotes.trim()}
                className={`text-xs px-4 py-2 rounded-md text-white font-semibold shadow-sm transition-all cursor-pointer ${
                  reviewAction.action === "REJECT"
                    ? "sylvar-btn-danger"
                    : "sylvar-btn-primary"
                } disabled:opacity-40`}
              >
                {reviewAction.action === "REJECT" ? "Confirm Rejection" : "Send Change Request"}
              </button>
            </div>
          </div>
        </div>
      )}
        </div>
      </main>
    </div>
  );
}
