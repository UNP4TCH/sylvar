-- ============================================================================
-- SYLVAR Database Migration: 004_human_review.sql
-- Domain G: Human Review, Approval Decisions & Compliance Certificates
-- ============================================================================

-- DOMAIN G: APPROVAL REQUESTS
CREATE TABLE IF NOT EXISTS approval_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    client_id UUID NOT NULL,
    asset_id UUID NOT NULL REFERENCES content_assets(id) ON DELETE CASCADE,
    asset_version_id UUID NOT NULL REFERENCES asset_versions(id) ON DELETE CASCADE,
    audit_run_id UUID NOT NULL REFERENCES audit_runs(id) ON DELETE RESTRICT,
    submitted_by_user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    assigned_to_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    status VARCHAR(25) NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED', 'CHANGES_REQUESTED')),
    decision_notes TEXT,
    advisory_acknowledgments JSONB NOT NULL DEFAULT '[]'::jsonb,
    decided_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    decided_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (workspace_id, client_id) REFERENCES client_brands(workspace_id, id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_approval_requests_client
    ON approval_requests (workspace_id, client_id, status, created_at DESC);

-- DOMAIN G: COMPLIANCE CERTIFICATES (Exportable Verifiable Manifests)
CREATE TABLE IF NOT EXISTS compliance_certificates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    client_id UUID NOT NULL,
    asset_version_id UUID NOT NULL REFERENCES asset_versions(id) ON DELETE CASCADE,
    approval_request_id UUID NOT NULL REFERENCES approval_requests(id) ON DELETE CASCADE,
    snapshot_hash VARCHAR(64) NOT NULL,
    certificate_hash VARCHAR(64) NOT NULL UNIQUE,
    certificate_payload JSONB NOT NULL,
    issued_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (workspace_id, client_id) REFERENCES client_brands(workspace_id, id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_compliance_cert_lookup
    ON compliance_certificates (workspace_id, client_id, asset_version_id);

-- ROW LEVEL SECURITY POLICIES (Resolves C-02: Aligns with custom backend JWT and public.current_app_* context)
ALTER TABLE approval_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE approval_requests FORCE ROW LEVEL SECURITY;

ALTER TABLE compliance_certificates ENABLE ROW LEVEL SECURITY;
ALTER TABLE compliance_certificates FORCE ROW LEVEL SECURITY;

CREATE POLICY approval_requests_access ON approval_requests
    FOR ALL
    USING (
        workspace_id = public.current_app_workspace_id()
        AND client_id = public.current_app_client_id()
    );

CREATE POLICY compliance_certificates_access ON compliance_certificates
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
