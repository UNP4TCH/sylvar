-- ============================================================================
-- SYLVAR Database Migration: 003_audit_engine.sql
-- Domain E: Content Asset Management
-- Domain F: Audit Runs, Engine Checks, Findings & Surgical Corrections
-- ============================================================================

-- DOMAIN E: CONTENT ASSETS
CREATE TABLE IF NOT EXISTS content_assets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    client_id UUID NOT NULL,
    title VARCHAR(255) NOT NULL,
    content_type VARCHAR(20) NOT NULL CHECK (content_type IN ('TEXT', 'IMAGE', 'HYBRID')),
    created_by_user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (workspace_id, client_id) REFERENCES client_brands(workspace_id, id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_content_assets_client
    ON content_assets (workspace_id, client_id, created_at DESC);

-- DOMAIN E: ASSET VERSIONS
CREATE TABLE IF NOT EXISTS asset_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    client_id UUID NOT NULL,
    asset_id UUID NOT NULL REFERENCES content_assets(id) ON DELETE CASCADE,
    version_number INTEGER NOT NULL,
    text_content TEXT,
    file_storage_path TEXT,
    sha256_hash VARCHAR(64) NOT NULL,
    created_from_correction_id UUID, -- self/remediation reference
    created_by_user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (asset_id, version_number),
    FOREIGN KEY (workspace_id, client_id) REFERENCES client_brands(workspace_id, id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_asset_versions_lookup
    ON asset_versions (workspace_id, client_id, asset_id, version_number DESC);

-- DOMAIN F: AUDIT RUNS
CREATE TABLE IF NOT EXISTS audit_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    client_id UUID NOT NULL,
    asset_id UUID NOT NULL REFERENCES content_assets(id) ON DELETE CASCADE,
    asset_version_id UUID NOT NULL REFERENCES asset_versions(id) ON DELETE CASCADE,
    snapshot_id UUID NOT NULL REFERENCES brand_memory_snapshots(id) ON DELETE RESTRICT,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED')),
    overall_verdict VARCHAR(20)
        CHECK (overall_verdict IN ('PASS', 'WARNINGS', 'BLOCKED')),
    error_details TEXT,
    triggered_by_user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    FOREIGN KEY (workspace_id, client_id) REFERENCES client_brands(workspace_id, id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_audit_runs_client
    ON audit_runs (workspace_id, client_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_audit_runs_version
    ON audit_runs (asset_version_id, created_at DESC);

-- DOMAIN F: AUDIT CHECKS (One row per engine execution per run)
CREATE TABLE IF NOT EXISTS audit_checks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    client_id UUID NOT NULL,
    audit_run_id UUID NOT NULL REFERENCES audit_runs(id) ON DELETE CASCADE,
    engine_type VARCHAR(30) NOT NULL
        CHECK (engine_type IN ('TERMINOLOGY', 'FACTUAL', 'VISUAL')),
    status VARCHAR(20) NOT NULL
        CHECK (status IN ('PASS', 'WARNING', 'FAIL')),
    execution_time_ms INTEGER NOT NULL DEFAULT 0,
    summary_details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (workspace_id, client_id) REFERENCES client_brands(workspace_id, id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_audit_checks_run
    ON audit_checks (audit_run_id);

-- DOMAIN F: AUDIT FINDINGS (Fine-grained diagnostic scorecard entries)
CREATE TABLE IF NOT EXISTS audit_findings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    client_id UUID NOT NULL,
    audit_run_id UUID NOT NULL REFERENCES audit_runs(id) ON DELETE CASCADE,
    check_id UUID NOT NULL REFERENCES audit_checks(id) ON DELETE CASCADE,
    rule_id UUID REFERENCES brand_rules(id) ON DELETE SET NULL,
    rule_code VARCHAR(100),
    severity VARCHAR(20) NOT NULL
        CHECK (severity IN ('CRITICAL', 'MAJOR', 'MINOR', 'ADVISORY')),
    message TEXT NOT NULL,
    location_start INTEGER,
    location_end INTEGER,
    snippet TEXT,
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (workspace_id, client_id) REFERENCES client_brands(workspace_id, id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_audit_findings_run
    ON audit_findings (audit_run_id, severity);

-- DOMAIN F: CORRECTION SUGGESTIONS (AI Surgical Remediation)
CREATE TABLE IF NOT EXISTS correction_suggestions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    client_id UUID NOT NULL,
    audit_run_id UUID NOT NULL REFERENCES audit_runs(id) ON DELETE CASCADE,
    finding_id UUID NOT NULL REFERENCES audit_findings(id) ON DELETE CASCADE,
    original_text TEXT NOT NULL,
    suggested_text TEXT NOT NULL,
    rationale TEXT NOT NULL,
    applied_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (workspace_id, client_id) REFERENCES client_brands(workspace_id, id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_corrections_finding
    ON correction_suggestions (finding_id);

-- Explicit Foreign Key for version remediation lineage (M-12)
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_asset_versions_correction'
    ) THEN
        ALTER TABLE asset_versions
            ADD CONSTRAINT fk_asset_versions_correction
            FOREIGN KEY (created_from_correction_id)
            REFERENCES correction_suggestions(id)
            ON DELETE SET NULL;
    END IF;
END $$;

-- ROW LEVEL SECURITY POLICIES (Resolves C-02: Aligns with custom backend JWT and public.current_app_* context)
ALTER TABLE content_assets ENABLE ROW LEVEL SECURITY;
ALTER TABLE content_assets FORCE ROW LEVEL SECURITY;

ALTER TABLE asset_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE asset_versions FORCE ROW LEVEL SECURITY;

ALTER TABLE audit_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_runs FORCE ROW LEVEL SECURITY;

ALTER TABLE audit_checks ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_checks FORCE ROW LEVEL SECURITY;

ALTER TABLE audit_findings ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_findings FORCE ROW LEVEL SECURITY;

ALTER TABLE correction_suggestions ENABLE ROW LEVEL SECURITY;
ALTER TABLE correction_suggestions FORCE ROW LEVEL SECURITY;

CREATE POLICY content_assets_access ON content_assets
    FOR ALL
    USING (
        workspace_id = public.current_app_workspace_id()
        AND client_id = public.current_app_client_id()
    );

CREATE POLICY asset_versions_access ON asset_versions
    FOR ALL
    USING (
        workspace_id = public.current_app_workspace_id()
        AND client_id = public.current_app_client_id()
    );

CREATE POLICY audit_runs_access ON audit_runs
    FOR ALL
    USING (
        workspace_id = public.current_app_workspace_id()
        AND client_id = public.current_app_client_id()
    );

CREATE POLICY audit_checks_access ON audit_checks
    FOR ALL
    USING (
        workspace_id = public.current_app_workspace_id()
        AND client_id = public.current_app_client_id()
    );

CREATE POLICY audit_findings_access ON audit_findings
    FOR ALL
    USING (
        workspace_id = public.current_app_workspace_id()
        AND client_id = public.current_app_client_id()
    );

CREATE POLICY correction_suggestions_access ON correction_suggestions
    FOR ALL
    USING (
        workspace_id = public.current_app_workspace_id()
        AND client_id = public.current_app_client_id()
    );

-- C-03: Revoke default PostgREST Data API exposure from anon & authenticated
DO $$ BEGIN
    IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'anon') THEN
        REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon;
        REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM anon;
        REVOKE ALL ON ALL ROUTINES IN SCHEMA public FROM anon;
    END IF;
    IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'authenticated') THEN
        REVOKE ALL ON ALL TABLES IN SCHEMA public FROM authenticated;
        REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM authenticated;
        REVOKE ALL ON ALL ROUTINES IN SCHEMA public FROM authenticated;
    END IF;
END $$;
