import { useEffect, useState } from "react";
import type { createAuthedClient } from "../lib/authedApi";
import { formatApiError } from "../lib/errors";

interface RuleViolationStat {
  rule_code: string;
  category: string;
  violation_count: number;
  affected_assets_count: number;
  severity: string;
  sample_snippet?: string | null;
}

interface TemporalTrendPoint {
  date: string;
  total_audits: number;
  passed_count: number;
  blocked_count: number;
  warnings_count: number;
}

interface RemediationAdoptionStat {
  total_suggestions_generated: number;
  applied_suggestions_count: number;
  adoption_rate_pct: number;
}

interface LongitudinalInsightsResponse {
  workspace_id: string;
  client_id: string;
  period_days: number;
  total_audits: number;
  pass_rate_pct: number;
  block_rate_pct: number;
  warnings_rate_pct: number;
  remediation_adoption: RemediationAdoptionStat;
  top_recurring_violations: RuleViolationStat[];
  temporal_trends: TemporalTrendPoint[];
  observed_insights: string[];
  inferred_recommendations: string[];
}

interface AnalyticsViewProps {
  api: ReturnType<typeof createAuthedClient>;
  workspaceId: string;
  clientId: string;
}

export default function AnalyticsView({
  api,
  workspaceId,
  clientId,
}: AnalyticsViewProps) {
  const [periodDays, setPeriodDays] = useState<number>(30);
  const [insights, setInsights] = useState<LongitudinalInsightsResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  async function loadAnalytics(days: number) {
    setLoading(true);
    setError(null);
    try {
      const data = await api.get<LongitudinalInsightsResponse>(
        `/api/v1/workspaces/${workspaceId}/clients/${clientId}/analytics/insights?days=${days}`
      );
      setInsights(data);
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (workspaceId && clientId) {
      void loadAnalytics(periodDays);
    }
  }, [workspaceId, clientId, periodDays]);

  return (
    <div className="space-y-6">
      {/* Header & Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-5 rounded-2xl bg-[#16151a] border border-[#232027]">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-xl">📊</span>
            <h2 className="text-base font-bold text-slate-100">Longitudinal Brand Compliance Insights</h2>
            <span className="px-2 py-0.5 text-[10px] font-mono tracking-wider font-semibold rounded bg-amber-500/10 text-amber-400 border border-amber-500/20">
              STAGE 3 DIFFERENTIATOR
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1 max-w-2xl">
            Tenant-scoped recurring violation patterns, pre-flight pass/block rates, surgical suggestion adoption, and temporal trends with strict separation between observed facts and inferred recommendations.
          </p>
        </div>

        {/* Period Selector */}
        <div className="flex items-center gap-1.5 p-1 rounded-xl bg-[#121115] border border-[#232027]">
          {[7, 30, 90].map((d) => (
            <button
              key={d}
              type="button"
              onClick={() => setPeriodDays(d)}
              className={`px-3 py-1.5 rounded-lg text-xs font-mono font-semibold transition-all ${
                periodDays === d
                  ? "bg-amber-500 text-slate-950 shadow font-bold"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              {d}d
            </button>
          ))}
          <button
            type="button"
            onClick={() => void loadAnalytics(periodDays)}
            className="p-1.5 text-slate-400 hover:text-amber-400 text-xs transition-colors"
            title="Refresh analytics"
            aria-label="Refresh analytics"
          >
            ↻
          </button>
        </div>
      </div>

      {/* Error state */}
      {error && (
        <div role="alert" className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-300 text-xs flex items-center justify-between">
          <span>{error}</span>
          <button
            type="button"
            onClick={() => void loadAnalytics(periodDays)}
            className="underline font-semibold text-rose-400 hover:text-rose-200"
          >
            Retry
          </button>
        </div>
      )}

      {/* Loading state */}
      {loading && !insights && (
        <div className="grid grid-cols-1 sm:grid-cols-4 gap-4 animate-pulse">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-28 rounded-2xl bg-[#16151a] border border-[#232027]" />
          ))}
        </div>
      )}

      {/* Insights Content */}
      {insights && (
        <div className="space-y-6">
          {/* KPI Summary Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {/* Total Audits */}
            <div className="p-5 rounded-2xl bg-[#16151a] border border-[#232027]">
              <div className="text-[11px] font-mono uppercase tracking-wider text-slate-400">Audits Evaluated</div>
              <div className="text-3xl font-extrabold text-slate-100 mt-2">{insights.total_audits}</div>
              <div className="text-[11px] text-slate-500 mt-1">Lookback window: {insights.period_days} days</div>
            </div>

            {/* Pass Rate */}
            <div className="p-5 rounded-2xl bg-[#16151a] border border-[#232027]">
              <div className="text-[11px] font-mono uppercase tracking-wider text-slate-400">Pre-Flight Pass Rate</div>
              <div className="text-3xl font-extrabold text-emerald-400 mt-2">{insights.pass_rate_pct.toFixed(1)}%</div>
              <div className="text-[11px] text-slate-500 mt-1">
                Blocked: <span className="text-rose-400">{insights.block_rate_pct.toFixed(1)}%</span> &bull; Warnings: <span className="text-amber-400">{insights.warnings_rate_pct.toFixed(1)}%</span>
              </div>
            </div>

            {/* Block Rate */}
            <div className="p-5 rounded-2xl bg-[#16151a] border border-[#232027]">
              <div className="text-[11px] font-mono uppercase tracking-wider text-slate-400">Governance Block Rate</div>
              <div className="text-3xl font-extrabold text-rose-400 mt-2">{insights.block_rate_pct.toFixed(1)}%</div>
              <div className="text-[11px] text-slate-500 mt-1">Non-compliant assets prevented</div>
            </div>

            {/* Remediation Adoption */}
            <div className="p-5 rounded-2xl bg-[#16151a] border border-[#232027]">
              <div className="text-[11px] font-mono uppercase tracking-wider text-slate-400">Remediation Adoption</div>
              <div className="text-3xl font-extrabold text-amber-400 mt-2">
                {insights.remediation_adoption.adoption_rate_pct.toFixed(1)}%
              </div>
              <div className="text-[11px] text-slate-500 mt-1">
                {insights.remediation_adoption.applied_suggestions_count} applied of {insights.remediation_adoption.total_suggestions_generated} suggested
              </div>
            </div>
          </div>

          {/* Epistemic Separation: Observed Facts vs Inferred Recommendations */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Section A: Observed Facts */}
            <div className="p-5 rounded-2xl bg-[#16151a] border border-emerald-500/20 space-y-3">
              <div className="flex items-center gap-2 border-b border-[#232027] pb-3">
                <span className="w-2.5 h-2.5 rounded-full bg-emerald-400" />
                <h3 className="text-xs font-bold font-mono uppercase tracking-wider text-emerald-400">
                  Observed Historical Metrics
                </h3>
              </div>
              <p className="text-[11px] text-slate-400 leading-relaxed">
                Empirical audit facts measured directly from client audit runs and surgical suggestion logs.
              </p>
              <ul className="space-y-2 pt-1">
                {insights.observed_insights.map((obs, i) => (
                  <li key={i} className="text-xs text-slate-300 flex items-start gap-2 bg-[#121115] p-2.5 rounded-xl border border-[#232027]">
                    <span className="text-emerald-400 font-bold">&bull;</span>
                    <span>{obs}</span>
                  </li>
                ))}
              </ul>
            </div>

            {/* Section B: Inferred Recommendations */}
            <div className="p-5 rounded-2xl bg-[#16151a] border border-amber-500/20 space-y-3">
              <div className="flex items-center gap-2 border-b border-[#232027] pb-3">
                <span className="w-2.5 h-2.5 rounded-full bg-amber-400" />
                <h3 className="text-xs font-bold font-mono uppercase tracking-wider text-amber-400">
                  Inferred Governance Recommendations
                </h3>
              </div>
              <p className="text-[11px] text-slate-400 leading-relaxed">
                Contextual, data-driven recommendations derived to improve upstream creator briefing and guideline quality.
              </p>
              <ul className="space-y-2 pt-1">
                {insights.inferred_recommendations.map((rec, i) => (
                  <li key={i} className="text-xs text-slate-300 flex items-start gap-2 bg-[#121115] p-2.5 rounded-xl border border-[#232027]">
                    <span className="text-amber-400 font-bold">&rarr;</span>
                    <span>{rec}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>

          {/* Top Recurring Violations */}
          <div className="p-5 rounded-2xl bg-[#16151a] border border-[#232027] space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-xs font-mono uppercase tracking-wider text-slate-300 font-bold">
                  Top Recurring Violations
                </h3>
                <p className="text-[11px] text-slate-500 mt-0.5">
                  Brand rules with highest frequency of pre-flight non-compliance across submitted creative assets.
                </p>
              </div>
              <span className="px-2.5 py-1 rounded text-xs font-mono text-slate-400 bg-[#121115] border border-[#232027]">
                {insights.top_recurring_violations.length} rules identified
              </span>
            </div>

            {insights.top_recurring_violations.length === 0 ? (
              <div className="text-center py-8 text-xs text-slate-500">
                No recurring rule violations recorded in this lookback window.
              </div>
            ) : (
              <div className="divide-y divide-[#232027]">
                {insights.top_recurring_violations.map((v, i) => (
                  <div key={i} className="py-3 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-xs font-bold text-slate-200">{v.rule_code}</span>
                        <span className="px-1.5 py-0.5 rounded text-[10px] font-mono font-semibold bg-slate-800 text-slate-400 border border-slate-700">
                          {v.category}
                        </span>
                        <span className={`px-1.5 py-0.5 rounded text-[10px] font-mono font-semibold ${
                          v.severity === "CRITICAL" ? "bg-rose-500/20 text-rose-400" : "bg-amber-500/20 text-amber-400"
                        }`}>
                          {v.severity}
                        </span>
                      </div>
                      {v.sample_snippet && (
                        <div className="text-[11px] text-slate-400 font-mono italic">
                          &ldquo;{v.sample_snippet}&rdquo;
                        </div>
                      )}
                    </div>

                    <div className="flex items-center gap-4 text-xs font-mono">
                      <div>
                        <span className="text-slate-500 text-[10px] block">VIOLATIONS</span>
                        <span className="text-rose-400 font-bold">{v.violation_count}</span>
                      </div>
                      <div>
                        <span className="text-slate-500 text-[10px] block">AFFECTED ASSETS</span>
                        <span className="text-slate-200 font-bold">{v.affected_assets_count}</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Temporal Trend Buckets */}
          {insights.temporal_trends.length > 0 && (
            <div className="p-5 rounded-2xl bg-[#16151a] border border-[#232027] space-y-4">
              <div>
                <h3 className="text-xs font-mono uppercase tracking-wider text-slate-300 font-bold">
                  Daily Temporal Distribution
                </h3>
                <p className="text-[11px] text-slate-500 mt-0.5">
                  Daily audit volumes and pre-publication compliance outcomes.
                </p>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs font-mono">
                  <thead>
                    <tr className="border-b border-[#232027] text-slate-500 text-[10px]">
                      <th className="py-2">DATE</th>
                      <th className="py-2">TOTAL AUDITS</th>
                      <th className="py-2 text-emerald-400">PASSED</th>
                      <th className="py-2 text-amber-400">WARNINGS</th>
                      <th className="py-2 text-rose-400">BLOCKED</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#232027]">
                    {insights.temporal_trends.map((pt, i) => (
                      <tr key={i} className="hover:bg-[#1b1921] transition-colors">
                        <td className="py-2 text-slate-300 font-semibold">{pt.date}</td>
                        <td className="py-2 text-slate-100">{pt.total_audits}</td>
                        <td className="py-2 text-emerald-400 font-bold">{pt.passed_count}</td>
                        <td className="py-2 text-amber-400 font-bold">{pt.warnings_count}</td>
                        <td className="py-2 text-rose-400 font-bold">{pt.blocked_count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
