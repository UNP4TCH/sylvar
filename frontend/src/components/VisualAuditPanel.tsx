interface Finding {
  finding_id: string;
  rule_code: string | null;
  severity: string;
  message: string;
  snippet: string | null;
  evidence: Record<string, unknown>;
}

interface AuditCheck {
  check_id: string;
  engine_type: string;
  status: string;
  execution_time_ms: number;
  summary_details?: Record<string, unknown>;
}

interface VisualAuditPanelProps {
  visualCheck?: AuditCheck;
  visualFindings: Finding[];
  imageUrl?: string | null;
}

export default function VisualAuditPanel({
  visualCheck,
  visualFindings,
  imageUrl,
}: VisualAuditPanelProps) {
  const summary = visualCheck?.summary_details ?? {};
  const dominantPalette = (summary.dominant_palette as string[]) ?? [];
  const wcagContrast = (summary.wcag_contrast as Record<string, unknown>) ?? {};
  const contrastRatio = wcagContrast.contrast_ratio as number | undefined;
  const isWcagCompliant = wcagContrast.compliant_aa as boolean | undefined;
  const c1Hex = (wcagContrast.c1_hex as string) ?? dominantPalette[0] ?? "#FFFFFF";
  const c2Hex = (wcagContrast.c2_hex as string) ?? dominantPalette[1] ?? "#000000";

  return (
    <div className="p-5 rounded-2xl bg-[#16151a] border border-[#232027] space-y-5">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#232027] pb-3">
        <div className="flex items-center gap-2">
          <span className="text-lg">🎨</span>
          <h3 className="text-sm font-bold text-slate-100">Multimodal Visual Brand Compliance</h3>
          <span className="px-2 py-0.5 text-[10px] font-mono tracking-wider font-semibold rounded bg-amber-500/10 text-amber-400 border border-amber-500/20">
            STAGE 3 DIFFERENTIATOR
          </span>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-[11px] font-mono text-slate-400">
            Status:
          </span>
          <span className={`px-2 py-0.5 rounded text-[10px] font-bold font-mono ${
            visualCheck?.status === "PASS"
              ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
              : visualCheck?.status === "WARNING"
              ? "bg-amber-500/20 text-amber-400 border border-amber-500/30"
              : "bg-slate-800 text-slate-400"
          }`}>
            {visualCheck?.status ?? "AUDITED"}
          </span>
          {visualCheck?.execution_time_ms !== undefined && (
            <span className="text-[10px] font-mono text-slate-500">
              {visualCheck.execution_time_ms}ms
            </span>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Left Column: Image Preview */}
        {imageUrl && (
          <div className="space-y-2">
            <span className="text-[11px] font-mono text-slate-400 uppercase tracking-wider block font-semibold">
              Asset Preview
            </span>
            <div className="rounded-xl overflow-hidden border border-[#2a2730] bg-[#121115] max-h-48 flex items-center justify-center p-2">
              <img
                src={imageUrl}
                alt="Submitted visual brand asset"
                className="max-h-44 object-contain rounded-lg"
              />
            </div>
          </div>
        )}

        {/* Center Column: Dominant Palette */}
        <div className={`space-y-3 ${imageUrl ? "lg:col-span-2" : "lg:col-span-3"}`}>
          <div>
            <span className="text-[11px] font-mono text-slate-400 uppercase tracking-wider block font-semibold">
              Extracted Dominant Color Palette (Excluding Matte Canvas)
            </span>
            <p className="text-[11px] text-slate-500 mt-0.5">
              Quantized dominant colors extracted from opaque pixels per ADR-008.
            </p>
          </div>

          {dominantPalette.length > 0 ? (
            <div className="flex flex-wrap items-center gap-3">
              {dominantPalette.map((hex, i) => (
                <div
                  key={i}
                  className="flex items-center gap-2 p-2 rounded-xl bg-[#121115] border border-[#232027]"
                >
                  <span
                    className="w-7 h-7 rounded-lg border border-white/20 shadow-sm"
                    style={{ backgroundColor: hex }}
                  />
                  <div>
                    <span className="text-xs font-mono font-bold text-slate-200 block">{hex}</span>
                    <span className="text-[9px] font-mono text-slate-500">Color {i + 1}</span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-xs text-slate-500 italic">No dominant palette extracted.</div>
          )}

          {/* WCAG 2.1 Contrast Indicator */}
          {contrastRatio !== undefined && (
            <div className="mt-4 p-4 rounded-xl bg-[#121115] border border-[#2a2730] space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-mono font-bold text-slate-300">
                  WCAG 2.1 Contrast Ratio
                </span>
                <span
                  className={`px-2 py-0.5 rounded text-[10px] font-bold font-mono ${
                    isWcagCompliant
                      ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                      : "bg-amber-500/20 text-amber-400 border border-amber-500/30"
                  }`}
                >
                  {isWcagCompliant ? "AA Compliant (≥ 4.5:1)" : "Below AA Threshold (< 4.5:1)"}
                </span>
              </div>

              <div className="flex items-center gap-4">
                <div className="flex items-center gap-2">
                  <div
                    className="w-10 h-10 rounded-lg border border-white/20 flex items-center justify-center font-bold text-xs shadow-inner"
                    style={{ backgroundColor: c1Hex, color: c2Hex }}
                  >
                    Aa
                  </div>
                  <div>
                    <span className="text-lg font-mono font-extrabold text-slate-100">
                      {contrastRatio.toFixed(2)}:1
                    </span>
                    <span className="text-[10px] text-slate-500 block">Relative Luminance Ratio</span>
                  </div>
                </div>

                <div className="text-[11px] text-slate-400 border-l border-[#232027] pl-4 space-y-0.5">
                  <div>
                    <span className="text-slate-500">Foreground:</span> <span className="font-mono text-slate-300">{c1Hex}</span>
                  </div>
                  <div>
                    <span className="text-slate-500">Background:</span> <span className="font-mono text-slate-300">{c2Hex}</span>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Visual Findings List */}
      {visualFindings.length > 0 && (
        <div className="space-y-2 border-t border-[#232027] pt-4">
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono uppercase tracking-wider text-slate-400 font-bold">
              Visual Compliance Findings ({visualFindings.length})
            </span>
            <span className="text-[10px] font-mono text-amber-400 bg-amber-500/10 px-2 py-0.5 rounded border border-amber-500/20">
              ADVISORY ONLY &bull; NEVER BLOCKS RELEASE
            </span>
          </div>

          <div className="space-y-2">
            {visualFindings.map((f, i) => (
              <div
                key={f.finding_id || i}
                className="p-3 rounded-xl bg-[#121115] border border-amber-500/20 text-xs flex flex-col sm:flex-row sm:items-center justify-between gap-3"
              >
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="px-1.5 py-0.5 rounded text-[10px] font-bold font-mono bg-amber-500/20 text-amber-400 border border-amber-500/30">
                      {f.severity}
                    </span>
                    <span className="font-mono text-[11px] text-slate-300 font-semibold">{f.rule_code}</span>
                  </div>
                  <p className="text-slate-300 text-[11px]">{f.message}</p>
                </div>

                {f.evidence && f.evidence.delta_e !== undefined && (
                  <div className="text-right font-mono text-xs flex-shrink-0">
                    <span className="text-[10px] text-slate-500 block">&Delta;E₀₀ COLOR DISTANCE</span>
                    <span className="text-amber-400 font-bold">
                      {Number(f.evidence.delta_e).toFixed(1)}
                    </span>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

