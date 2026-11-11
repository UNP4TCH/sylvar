import { useState } from "react";
import type { createAuthedClient } from "../lib/authedApi";
import { formatApiError } from "../lib/errors";

interface RuleExcerpt {
  rule_id: string;
  rule_code: string;
  category: string;
  statement: string;
  forbidden_term?: string | null;
  preferred_term?: string | null;
  hex_code?: string | null;
  source_document?: string | null;
  section?: string | null;
}

interface ContradictionItem {
  conflict_id: string;
  conflict_type: string;
  severity: string;
  explanation: string;
  rule_a: RuleExcerpt;
  rule_b: RuleExcerpt;
  suggested_resolutions?: string[];
}

interface ContradictionScanResponse {
  workspace_id: string;
  client_id: string;
  rules_scanned_count: number;
  contradictions_count: number;
  has_critical_conflicts: boolean;
  contradictions: ContradictionItem[];
}

interface ResolutionResponse {
  conflict_id: string;
  status: string;
  resolution_action: string;
  resolution_notes: string;
  retained_rule_id?: string | null;
  deprecated_rule_id?: string | null;
  message: string;
}

interface ContradictionsViewProps {
  api: ReturnType<typeof createAuthedClient>;
  workspaceId: string;
  clientId: string;
  isBrandManager: boolean;
}

export default function ContradictionsView({
  api,
  workspaceId,
  clientId,
  isBrandManager,
}: ContradictionsViewProps) {
  const [scanResult, setScanResult] = useState<ContradictionScanResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Resolution state
  const [activeConflictId, setActiveConflictId] = useState<string | null>(null);
  const [resolutionAction, setResolutionAction] = useState<"KEEP_A" | "KEEP_B" | "MANUAL_OVERRIDE">("KEEP_A");
  const [customStatement, setCustomStatement] = useState("");
  const [resolutionNotes, setResolutionNotes] = useState("");
  const [resolving, setResolving] = useState(false);

  async function handleScan() {
    setLoading(true);
    setError(null);
    setSuccessMessage(null);
    try {
      const data = await api.post<ContradictionScanResponse>(
        `/api/v1/workspaces/${workspaceId}/clients/${clientId}/contradictions/scan`
      );
      setScanResult(data);
      if (data.contradictions_count === 0) {
        setSuccessMessage(`Scanned ${data.rules_scanned_count} rules. No guideline contradictions detected!`);
      }
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setLoading(false);
    }
  }

  async function handleResolve(conflict: ContradictionItem) {
    if (!resolutionNotes.trim() || resolutionNotes.trim().length < 5) {
      setError("Please provide a resolution rationale of at least 5 characters.");
      return;
    }
    if (resolutionAction === "MANUAL_OVERRIDE" && !customStatement.trim()) {
      setError("Please provide a custom synthesized guideline statement.");
      return;
    }

    setResolving(true);
    setError(null);
    try {
      const res = await api.post<ResolutionResponse>(
        `/api/v1/workspaces/${workspaceId}/clients/${clientId}/contradictions/${conflict.conflict_id}/resolve`,
        {
          resolution_action: resolutionAction,
          custom_statement: resolutionAction === "MANUAL_OVERRIDE" ? customStatement : undefined,
          resolution_notes: resolutionNotes,
        }
      );
      setSuccessMessage(res.message);
      // Remove resolved conflict from scan list
      if (scanResult) {
        const remaining = scanResult.contradictions.filter((c) => c.conflict_id !== conflict.conflict_id);
        setScanResult({
          ...scanResult,
          contradictions: remaining,
          contradictions_count: remaining.length,
          has_critical_conflicts: remaining.some((c) => c.severity === "CRITICAL"),
        });
      }
      setActiveConflictId(null);
      setResolutionNotes("");
      setCustomStatement("");
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setResolving(false);
    }
  }

  return (
    <div className="space-y-6">
      {/* Header & Scanner Trigger */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-5 rounded-2xl bg-[#16151a] border border-[#232027]">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-xl">⚡</span>
            <h2 className="text-base font-bold text-slate-100">Guideline Contradiction Scanner</h2>
            <span className="px-2 py-0.5 text-[10px] font-mono tracking-wider font-semibold rounded bg-amber-500/10 text-amber-400 border border-amber-500/20">
              STAGE 3 DIFFERENTIATOR
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1 max-w-2xl">
            Detects inverted terminology conflicts, mandate collisions, color specification clashes (&Delta;E &gt; 10), and factual claim discrepancies across approved memory rules and pending candidates.
          </p>
        </div>

        <button
          type="button"
          onClick={handleScan}
          disabled={loading}
          className="px-4 py-2.5 rounded-xl bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 hover:to-amber-500 text-slate-950 font-bold text-xs shadow-lg shadow-amber-500/20 flex items-center justify-center gap-2 disabled:opacity-50 transition-all focus:outline-none focus:ring-2 focus:ring-amber-500"
          aria-label="Scan Brand Guidelines for Contradictions"
        >
          {loading ? (
            <>
              <span className="w-3.5 h-3.5 border-2 border-slate-950/20 border-t-slate-950 rounded-full animate-spin" />
              Scanning Guidelines...
            </>
          ) : (
            <>
              <span>⚡</span> Scan Guidelines
            </>
          )}
        </button>
      </div>

      {/* Notifications */}
      {error && (
        <div role="alert" className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-300 text-xs flex items-start justify-between gap-3">
          <div className="flex items-start gap-2">
            <span className="text-rose-400 font-bold">✕</span>
            <span>{error}</span>
          </div>
          <button type="button" onClick={() => setError(null)} className="text-rose-400 hover:text-rose-200">
            &times;
          </button>
        </div>
      )}

      {successMessage && (
        <div role="status" className="p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-300 text-xs flex items-start justify-between gap-3">
          <div className="flex items-start gap-2">
            <span className="text-emerald-400 font-bold">✓</span>
            <span>{successMessage}</span>
          </div>
          <button type="button" onClick={() => setSuccessMessage(null)} className="text-emerald-400 hover:text-emerald-200">
            &times;
          </button>
        </div>
      )}

      {/* Scan Overview Stats */}
      {scanResult && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div className="p-4 rounded-xl bg-[#16151a] border border-[#232027]">
            <div className="text-[11px] font-mono uppercase text-slate-400">Rules Analyzed</div>
            <div className="text-2xl font-bold text-slate-100 mt-1">{scanResult.rules_scanned_count}</div>
          </div>
          <div className="p-4 rounded-xl bg-[#16151a] border border-[#232027]">
            <div className="text-[11px] font-mono uppercase text-slate-400">Contradictions Found</div>
            <div className={`text-2xl font-bold mt-1 ${scanResult.contradictions_count > 0 ? "text-rose-400" : "text-emerald-400"}`}>
              {scanResult.contradictions_count}
            </div>
          </div>
          <div className="p-4 rounded-xl bg-[#16151a] border border-[#232027]">
            <div className="text-[11px] font-mono uppercase text-slate-400">Critical Status</div>
            <div className="mt-1">
              {scanResult.has_critical_conflicts ? (
                <span className="px-2 py-1 rounded text-xs font-bold bg-rose-500/20 text-rose-400 border border-rose-500/30">
                  Critical Contradiction
                </span>
              ) : (
                <span className="px-2 py-1 rounded text-xs font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                  Harmonious
                </span>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Contradiction Cards */}
      {scanResult && scanResult.contradictions.length > 0 && (
        <div className="space-y-4">
          <h3 className="text-xs font-mono uppercase tracking-wider text-slate-400 font-semibold">
            Detected Guideline Conflicts ({scanResult.contradictions.length})
          </h3>

          {scanResult.contradictions.map((c) => {
            const isResolvingThis = activeConflictId === c.conflict_id;

            return (
              <div
                key={c.conflict_id}
                className="p-5 rounded-2xl bg-[#16151a] border border-rose-500/30 shadow-lg space-y-4"
              >
                {/* Conflict Header */}
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#232027] pb-3">
                  <div className="flex items-center gap-2">
                    <span className={`px-2 py-0.5 rounded text-[10px] font-bold font-mono tracking-wider ${
                      c.severity === "CRITICAL" ? "bg-rose-500/20 text-rose-400 border border-rose-500/30" : "bg-amber-500/20 text-amber-400 border border-amber-500/30"
                    }`}>
                      {c.severity}
                    </span>
                    <span className="px-2 py-0.5 rounded text-[10px] font-bold font-mono tracking-wider bg-slate-800 text-slate-300 border border-slate-700">
                      {c.conflict_type}
                    </span>
                    <span className="text-xs font-mono text-slate-400">ID: {c.conflict_id}</span>
                  </div>

                  {isBrandManager && (
                    <button
                      type="button"
                      onClick={() => {
                        setActiveConflictId(isResolvingThis ? null : c.conflict_id);
                        setResolutionAction("KEEP_A");
                        setCustomStatement("");
                        setResolutionNotes("");
                      }}
                      className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-amber-500/10 text-amber-300 hover:bg-amber-500/20 border border-amber-500/30 transition-colors"
                    >
                      {isResolvingThis ? "Cancel Resolution" : "Resolve Conflict"}
                    </button>
                  )}
                </div>

                {/* Explanation */}
                <p className="text-xs text-slate-300 leading-relaxed font-medium">
                  {c.explanation}
                </p>

                {/* Side-by-Side Rule Excerpts */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {/* Rule A */}
                  <div className="p-4 rounded-xl bg-[#1a191f] border border-[#2a2730] space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-[11px] font-mono font-bold text-amber-400">RULE A: {c.rule_a.rule_code}</span>
                      <span className="text-[10px] font-mono text-slate-500">{c.rule_a.category}</span>
                    </div>
                    <div className="text-xs text-slate-200 bg-[#121115] p-2.5 rounded-lg border border-[#232027] font-mono">
                      {c.rule_a.statement}
                    </div>
                    {c.rule_a.forbidden_term && (
                      <div className="text-[11px] text-rose-300">
                        <span className="font-semibold text-rose-400">Forbidden:</span> &lsquo;{c.rule_a.forbidden_term}&rsquo;
                      </div>
                    )}
                    {c.rule_a.preferred_term && (
                      <div className="text-[11px] text-emerald-300">
                        <span className="font-semibold text-emerald-400">Mandated:</span> &lsquo;{c.rule_a.preferred_term}&rsquo;
                      </div>
                    )}
                    {c.rule_a.hex_code && (
                      <div className="flex items-center gap-2 text-[11px] text-slate-300">
                        <span className="w-3.5 h-3.5 rounded border border-white/20" style={{ backgroundColor: c.rule_a.hex_code }} />
                        <span className="font-mono">{c.rule_a.hex_code}</span>
                      </div>
                    )}
                  </div>

                  {/* Rule B */}
                  <div className="p-4 rounded-xl bg-[#1a191f] border border-[#2a2730] space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-[11px] font-mono font-bold text-indigo-400">RULE B: {c.rule_b.rule_code}</span>
                      <span className="text-[10px] font-mono text-slate-500">{c.rule_b.category}</span>
                    </div>
                    <div className="text-xs text-slate-200 bg-[#121115] p-2.5 rounded-lg border border-[#232027] font-mono">
                      {c.rule_b.statement}
                    </div>
                    {c.rule_b.forbidden_term && (
                      <div className="text-[11px] text-rose-300">
                        <span className="font-semibold text-rose-400">Forbidden:</span> &lsquo;{c.rule_b.forbidden_term}&rsquo;
                      </div>
                    )}
                    {c.rule_b.preferred_term && (
                      <div className="text-[11px] text-emerald-300">
                        <span className="font-semibold text-emerald-400">Mandated:</span> &lsquo;{c.rule_b.preferred_term}&rsquo;
                      </div>
                    )}
                    {c.rule_b.hex_code && (
                      <div className="flex items-center gap-2 text-[11px] text-slate-300">
                        <span className="w-3.5 h-3.5 rounded border border-white/20" style={{ backgroundColor: c.rule_b.hex_code }} />
                        <span className="font-mono">{c.rule_b.hex_code}</span>
                      </div>
                    )}
                  </div>
                </div>

                {/* Human Resolution Workflow Panel */}
                {isResolvingThis && (
                  <div className="mt-4 p-4 rounded-xl bg-[#1f1d24] border border-amber-500/30 space-y-4">
                    <div className="text-xs font-bold text-amber-300 flex items-center gap-2">
                      <span>⚖</span> Human Resolution Accountability (ADR-004)
                    </div>
                    <p className="text-[11px] text-slate-400 leading-relaxed">
                      Select the authoritative resolution strategy. SYLVAR never silently overwrites guidelines; all resolutions require explicit Brand Manager sign-off and persist in the audit ledger.
                    </p>

                    {/* Strategy selection */}
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                      <button
                        type="button"
                        onClick={() => setResolutionAction("KEEP_A")}
                        className={`p-3 rounded-xl border text-left transition-all ${
                          resolutionAction === "KEEP_A"
                            ? "border-amber-500 bg-amber-500/10 text-amber-200 shadow"
                            : "border-[#2a2730] bg-[#16151a] text-slate-400 hover:border-slate-600"
                        }`}
                      >
                        <div className="text-xs font-bold">Retain Rule A</div>
                        <div className="text-[10px] mt-0.5 opacity-80">Keep [{c.rule_a.rule_code}], deprecate Rule B</div>
                      </button>

                      <button
                        type="button"
                        onClick={() => setResolutionAction("KEEP_B")}
                        className={`p-3 rounded-xl border text-left transition-all ${
                          resolutionAction === "KEEP_B"
                            ? "border-amber-500 bg-amber-500/10 text-amber-200 shadow"
                            : "border-[#2a2730] bg-[#16151a] text-slate-400 hover:border-slate-600"
                        }`}
                      >
                        <div className="text-xs font-bold">Retain Rule B</div>
                        <div className="text-[10px] mt-0.5 opacity-80">Keep [{c.rule_b.rule_code}], deprecate Rule A</div>
                      </button>

                      <button
                        type="button"
                        onClick={() => setResolutionAction("MANUAL_OVERRIDE")}
                        className={`p-3 rounded-xl border text-left transition-all ${
                          resolutionAction === "MANUAL_OVERRIDE"
                            ? "border-amber-500 bg-amber-500/10 text-amber-200 shadow"
                            : "border-[#2a2730] bg-[#16151a] text-slate-400 hover:border-slate-600"
                        }`}
                      >
                        <div className="text-xs font-bold">Manual Synthesis</div>
                        <div className="text-[10px] mt-0.5 opacity-80">Author a new unified guideline</div>
                      </button>
                    </div>

                    {resolutionAction === "MANUAL_OVERRIDE" && (
                      <div className="space-y-1">
                        <label htmlFor="custom-stmt-input" className="text-[11px] font-semibold text-slate-300">
                          Unified Guideline Statement <span className="text-rose-400">*</span>
                        </label>
                        <input
                          id="custom-stmt-input"
                          type="text"
                          value={customStatement}
                          onChange={(e) => setCustomStatement(e.target.value)}
                          placeholder="e.g., Primary brand color is #0F172A with #FF7700 reserved for callouts"
                          className="w-full px-3 py-2 text-xs rounded-lg bg-[#141317] border border-[#2a2730] text-slate-200 focus:outline-none focus:ring-1 focus:ring-amber-500"
                        />
                      </div>
                    )}

                    <div className="space-y-1">
                      <label htmlFor="res-notes-input" className="text-[11px] font-semibold text-slate-300">
                        Resolution Rationale &amp; Notes <span className="text-rose-400">*</span>
                      </label>
                      <textarea
                        id="res-notes-input"
                        value={resolutionNotes}
                        onChange={(e) => setResolutionNotes(e.target.value)}
                        placeholder="Explain governance rationale for audit ledger (minimum 5 characters)..."
                        rows={2}
                        className="w-full px-3 py-2 text-xs rounded-lg bg-[#141317] border border-[#2a2730] text-slate-200 focus:outline-none focus:ring-1 focus:ring-amber-500"
                      />
                    </div>

                    <div className="flex justify-end gap-2 pt-2">
                      <button
                        type="button"
                        onClick={() => setActiveConflictId(null)}
                        className="px-3 py-1.5 rounded-lg text-xs font-semibold text-slate-400 hover:text-slate-200 transition-colors"
                      >
                        Cancel
                      </button>
                      <button
                        type="button"
                        onClick={() => handleResolve(c)}
                        disabled={resolving || resolutionNotes.trim().length < 5}
                        className="px-4 py-1.5 rounded-lg bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-xs shadow disabled:opacity-50 transition-all"
                      >
                        {resolving ? "Recording Decision..." : "Commit Resolution"}
                      </button>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Empty Initial State */}
      {!scanResult && !loading && (
        <div className="text-center py-12 px-4 rounded-2xl bg-[#16151a] border border-[#232027] space-y-3">
          <div className="text-3xl">⚡</div>
          <h3 className="text-sm font-bold text-slate-200">No Guideline Contradiction Scan Active</h3>
          <p className="text-xs text-slate-400 max-w-md mx-auto">
            Click &ldquo;Scan Guidelines&rdquo; to analyze all approved Brand Rules and pending Candidate extractions for terminology conflicts, color clashes, or factual claim discrepancies.
          </p>
        </div>
      )}
    </div>
  );
}
