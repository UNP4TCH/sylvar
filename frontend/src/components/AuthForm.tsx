import { useState, type FormEvent } from "react";

interface Props {
  onSignIn: (email: string, password: string) => Promise<void>;
  onSignUp: (email: string, password: string) => Promise<void>;
  error: string | null;
  notice?: string | null;
  onModeChange?: () => void;
}

export default function AuthForm({ onSignIn, onSignUp, error, notice, onModeChange }: Props) {
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    try {
      await (mode === "signin" ? onSignIn : onSignUp)(email.trim(), password);
    } finally {
      setBusy(false);
    }
  }

  function toggle() {
    setMode(mode === "signin" ? "signup" : "signin");
    onModeChange?.();
  }

  return (
    <div className="auth-shell">
      {/* Left Column: Premium Brand & Governance Presentation */}
      <section className="auth-brand-panel" aria-label="SYLVAR Platform Overview">
        <div className="auth-brand-header">
          <div className="auth-brand-logo">
            <span className="auth-brand-mark">S</span>
            <div className="auth-brand-text">
              <strong className="auth-brand-name">SYLVAR</strong>
              <small className="auth-brand-subtitle">BRAND INTEGRITY PLATFORM</small>
            </div>
          </div>
          <span className="auth-brand-pill">
            <span className="auth-pulse-dot" /> Enterprise CI/CD
          </span>
        </div>

        <div className="auth-hero-copy">
          <p className="auth-eyebrow">PRE-PUBLICATION GOVERNANCE</p>
          <h1 className="auth-headline">
            Create with confidence.<br />
            <span className="auth-headline-accent">Publish with integrity.</span>
          </h1>
          <p className="auth-description">
            The automated pre-publication CI/CD platform that transforms guidelines into
            executable rules, runs multi-engine audits, and verifies independent approvals
            before publication.
          </p>
        </div>

        {/* Governance Workflow Pipeline Steps */}
        <div className="auth-workflow-card">
          <div className="auth-workflow-header">
            <span>GOVERNANCE WORKFLOW PIPELINE</span>
            <span className="auth-workflow-badge">ADR-004 ENFORCED</span>
          </div>

          <div className="auth-steps-list">
            <div className="auth-step-item">
              <div className="auth-step-num">01</div>
              <div className="auth-step-content">
                <strong>Living Brand Memory</strong>
                <p>Approved guidelines transformed into immutable, executable brand knowledge.</p>
              </div>
            </div>

            <div className="auth-step-item">
              <div className="auth-step-num">02</div>
              <div className="auth-step-content">
                <strong>Multi-Tier Audit Studio</strong>
                <p>Rule-based, factual consistency, and tone &amp; voice pre-publication auditing.</p>
              </div>
            </div>

            <div className="auth-step-item">
              <div className="auth-step-num">03</div>
              <div className="auth-step-content">
                <strong>Separation of Duties</strong>
                <p>Role-scoped review queue enforcing mandatory comments and preventing self-approval.</p>
              </div>
            </div>

            <div className="auth-step-item">
              <div className="auth-step-num">04</div>
              <div className="auth-step-content">
                <strong>Compliance Approval</strong>
                <p>Cryptographically verified compliance certificates issued for publication.</p>
              </div>
            </div>
          </div>
        </div>

        <div className="auth-status-proof">
          <span className="auth-live-dot" />
          <span>Living Brand Memory &amp; Audit Engine Operational</span>
        </div>
      </section>

      {/* Right Column: Secure Authentication Form */}
      <section className="auth-form-panel">
        <form onSubmit={(e) => void submit(e)} className="auth-card">
          <div className="auth-card-heading">
            <p className="auth-card-badge">SECURE WORKSPACE</p>
            <h2 className="auth-title">
              {mode === "signin" ? "Sign in" : "Create account"}
            </h2>
            <p className="auth-subtitle">
              {mode === "signin"
                ? "Sign in to continue to your governance workspace."
                : "Create your workspace to govern every publication with confidence."}
            </p>
          </div>

          {/* Error and Notice Alerts */}
          {error && (
            <div role="alert" className="auth-feedback auth-error">
              <span className="auth-feedback-icon" aria-hidden="true">⚠️</span>
              <div>
                <strong>Authentication error:</strong> {error}
              </div>
            </div>
          )}

          {notice && (
            <div role="status" className="auth-feedback auth-notice">
              <span className="auth-feedback-icon" aria-hidden="true">✓</span>
              <div>
                <strong>Notice:</strong> {notice}
              </div>
            </div>
          )}

          {/* Form Fields */}
          <div className="auth-fields-stack">
            <div className="auth-field-group">
              <label htmlFor="auth-email" className="auth-label">
                Email
              </label>
              <div className="auth-input-wrapper">
                <input
                  id="auth-email"
                  type="email"
                  required
                  autoComplete="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="name@company.com"
                  className="auth-input"
                  disabled={busy}
                  autoFocus
                />
              </div>
            </div>

            <div className="auth-field-group">
              <label htmlFor="auth-password" className="auth-label">
                Password
              </label>
              <div className="auth-input-wrapper">
                <input
                  id="auth-password"
                  type={showPassword ? "text" : "password"}
                  required
                  autoComplete={mode === "signin" ? "current-password" : "new-password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder={mode === "signin" ? "Enter your password" : "Create your password"}
                  className="auth-input"
                  style={{ paddingRight: "40px" }}
                  disabled={busy}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="auth-password-toggle"
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  title={showPassword ? "Hide password" : "Show password"}
                >
                  {showPassword ? (
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l18 18" />
                    </svg>
                  ) : (
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                    </svg>
                  )}
                </button>
              </div>
            </div>
          </div>

          {/* Primary Action Button */}
          <button
            type="submit"
            disabled={busy}
            className="auth-submit-btn"
          >
            {busy ? (
              <span className="auth-btn-spinner-content">
                <svg className="animate-spin h-4 w-4 text-current" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                </svg>
                Processing…
              </span>
            ) : mode === "signin" ? (
              "Sign in"
            ) : (
              "Sign up"
            )}
          </button>

          {/* Secondary Switch Mode */}
          <div className="auth-divider">
            <span className="auth-divider-line" />
            <span className="auth-divider-text">OR</span>
            <span className="auth-divider-line" />
          </div>

          <button
            type="button"
            className="auth-toggle-btn"
            onClick={toggle}
            disabled={busy}
          >
            {mode === "signin" ? "Need an account? Sign up" : "Have an account? Sign in"}
          </button>

          <p className="auth-footnote">
            Use your organization-approved account. Access is governed by workspace membership and client assignments.
          </p>
        </form>
      </section>
    </div>
  );
}
