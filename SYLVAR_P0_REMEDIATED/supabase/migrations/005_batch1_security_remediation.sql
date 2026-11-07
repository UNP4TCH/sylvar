-- =====================================================================
-- SYLVAR Batch 1 Database Security Remediation Migration
-- Version: 005_batch1_security_remediation.sql
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. Create Dedicated Runtime Role: sylvar_app_user
-- ---------------------------------------------------------------------
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sylvar_app_user') THEN
        CREATE ROLE sylvar_app_user WITH 
            LOGIN 
            NOSUPERUSER 
            NOBYPASSRLS 
            NOCREATEDB 
            NOCREATEROLE 
            NOREPLICATION;
    END IF;
END $$;

-- ---------------------------------------------------------------------
-- 2. Database & Schema Least-Privilege Grants
-- ---------------------------------------------------------------------
GRANT CONNECT ON DATABASE postgres TO sylvar_app_user;
GRANT USAGE ON SCHEMA public TO sylvar_app_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO sylvar_app_user;

-- Grant EXECUTE on explicit tenant context functions
GRANT EXECUTE ON FUNCTION public.current_app_user_id() TO sylvar_app_user;
GRANT EXECUTE ON FUNCTION public.current_app_workspace_id() TO sylvar_app_user;
GRANT EXECUTE ON FUNCTION public.current_app_client_id() TO sylvar_app_user;

-- Explicit Table Permissions:
-- Mutable Tables: SELECT, INSERT, UPDATE (ZERO DELETE)
GRANT SELECT, INSERT, UPDATE ON public.agency_workspaces TO sylvar_app_user;
GRANT SELECT, INSERT, UPDATE ON public.approval_requests TO sylvar_app_user;
GRANT SELECT, INSERT, UPDATE ON public.audit_runs TO sylvar_app_user;
GRANT SELECT, INSERT, UPDATE ON public.brand_memory_versions TO sylvar_app_user;
GRANT SELECT, INSERT, UPDATE ON public.brand_rules TO sylvar_app_user;
GRANT SELECT, INSERT, UPDATE ON public.client_brands TO sylvar_app_user;
GRANT SELECT, INSERT, UPDATE ON public.client_memberships TO sylvar_app_user;
GRANT SELECT, INSERT, UPDATE ON public.content_assets TO sylvar_app_user;
GRANT SELECT, INSERT, UPDATE ON public.extracted_candidates TO sylvar_app_user;
GRANT SELECT, INSERT, UPDATE ON public.guideline_documents TO sylvar_app_user;
GRANT SELECT, INSERT, UPDATE ON public.users TO sylvar_app_user;
GRANT SELECT, INSERT, UPDATE ON public.workspace_memberships TO sylvar_app_user;

-- Append-Only / Immutable Tables: SELECT, INSERT (ZERO UPDATE, ZERO DELETE)
GRANT SELECT, INSERT ON public.asset_versions TO sylvar_app_user;
GRANT SELECT, INSERT ON public.audit_checks TO sylvar_app_user;
GRANT SELECT, INSERT ON public.audit_findings TO sylvar_app_user;
GRANT SELECT, INSERT ON public.brand_memory_snapshots TO sylvar_app_user;
GRANT SELECT, INSERT ON public.brand_memory_version_rules TO sylvar_app_user;
GRANT SELECT, INSERT ON public.brand_rule_revisions TO sylvar_app_user;
GRANT SELECT, INSERT ON public.compliance_certificates TO sylvar_app_user;
GRANT SELECT, INSERT ON public.correction_suggestions TO sylvar_app_user;
GRANT SELECT, INSERT ON public.document_sections TO sylvar_app_user;

-- ---------------------------------------------------------------------
-- 3. Patch B1: Unique Certificate Constraint
-- ---------------------------------------------------------------------
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'uq_compliance_cert_approval_request'
          AND conrelid = 'public.compliance_certificates'::regclass
    ) THEN
        ALTER TABLE public.compliance_certificates
            ADD CONSTRAINT uq_compliance_cert_approval_request UNIQUE (approval_request_id);
    END IF;
END $$;

-- ---------------------------------------------------------------------
-- 4. Patch B2: public.users RLS Policies
-- ---------------------------------------------------------------------
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.users FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation_users ON public.users;
DROP POLICY IF EXISTS users_select_policy ON public.users;
DROP POLICY IF EXISTS users_insert_policy ON public.users;
DROP POLICY IF EXISTS users_update_policy ON public.users;
DROP POLICY IF EXISTS users_delete_policy ON public.users;

CREATE POLICY users_select_policy ON public.users
    FOR SELECT
    TO sylvar_app_user, authenticated
    USING (
        id = public.current_app_user_id()
        OR (
            public.current_app_user_id() IS NOT NULL
            AND EXISTS (
                SELECT 1 FROM public.workspace_memberships wm_inv
                WHERE wm_inv.user_id = users.id
                  AND wm_inv.status = 'INVITED'
                  AND wm_inv.revoked_at IS NULL
            )
        )
        OR (
            public.current_app_workspace_id() IS NOT NULL
            AND EXISTS (
                SELECT 1 FROM public.workspace_memberships wm_caller
                WHERE wm_caller.workspace_id = public.current_app_workspace_id()
                  AND wm_caller.user_id = public.current_app_user_id()
                  AND wm_caller.status = 'ACTIVE'
                  AND wm_caller.revoked_at IS NULL
            )
            AND EXISTS (
                SELECT 1 FROM public.workspace_memberships wm_target
                WHERE wm_target.workspace_id = public.current_app_workspace_id()
                  AND wm_target.user_id = users.id
                  AND wm_target.status = 'ACTIVE'
                  AND wm_target.revoked_at IS NULL
            )
        )
    );

CREATE POLICY users_insert_policy ON public.users
    FOR INSERT
    TO sylvar_app_user, authenticated
    WITH CHECK (
        id = public.current_app_user_id()
    );

CREATE POLICY users_update_policy ON public.users
    FOR UPDATE
    TO sylvar_app_user, authenticated
    USING (
        id = public.current_app_user_id()
        OR (
            public.current_app_user_id() IS NOT NULL
            AND EXISTS (
                SELECT 1 FROM public.workspace_memberships wm_inv
                WHERE wm_inv.user_id = users.id
                  AND wm_inv.status = 'INVITED'
                  AND wm_inv.revoked_at IS NULL
            )
        )
    )
    WITH CHECK (
        id = public.current_app_user_id()
    );
-- users_delete_policy intentionally omitted (ZERO DELETE)

-- ---------------------------------------------------------------------
-- 5. Patch B3: public.client_brands RLS Policies
-- ---------------------------------------------------------------------
ALTER TABLE public.client_brands ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.client_brands FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation_client_brands ON public.client_brands;
DROP POLICY IF EXISTS client_brands_select_policy ON public.client_brands;
DROP POLICY IF EXISTS client_brands_insert_policy ON public.client_brands;
DROP POLICY IF EXISTS client_brands_update_policy ON public.client_brands;
DROP POLICY IF EXISTS client_brands_delete_policy ON public.client_brands;

CREATE POLICY client_brands_select_policy ON public.client_brands
    FOR SELECT
    TO sylvar_app_user, authenticated
    USING (
        EXISTS (
            SELECT 1 FROM public.workspace_memberships wm
            WHERE wm.workspace_id = client_brands.workspace_id
              AND wm.user_id = public.current_app_user_id()
              AND wm.role = 'WORKSPACE_ADMIN'
              AND wm.status = 'ACTIVE'
              AND wm.revoked_at IS NULL
        )
        OR EXISTS (
            SELECT 1 FROM public.client_memberships cm
            WHERE cm.workspace_id = client_brands.workspace_id
              AND cm.client_id = client_brands.id
              AND cm.user_id = public.current_app_user_id()
              AND cm.status = 'ACTIVE'
              AND cm.revoked_at IS NULL
        )
    );

CREATE POLICY client_brands_insert_policy ON public.client_brands
    FOR INSERT
    TO sylvar_app_user, authenticated
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM public.workspace_memberships wm
            WHERE wm.workspace_id = client_brands.workspace_id
              AND wm.user_id = public.current_app_user_id()
              AND wm.role = 'WORKSPACE_ADMIN'
              AND wm.status = 'ACTIVE'
              AND wm.revoked_at IS NULL
        )
    );

CREATE POLICY client_brands_update_policy ON public.client_brands
    FOR UPDATE
    TO sylvar_app_user, authenticated
    USING (
        EXISTS (
            SELECT 1 FROM public.workspace_memberships wm
            WHERE wm.workspace_id = client_brands.workspace_id
              AND wm.user_id = public.current_app_user_id()
              AND wm.role = 'WORKSPACE_ADMIN'
              AND wm.status = 'ACTIVE'
              AND wm.revoked_at IS NULL
        )
    )
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM public.workspace_memberships wm
            WHERE wm.workspace_id = client_brands.workspace_id
              AND wm.user_id = public.current_app_user_id()
              AND wm.role = 'WORKSPACE_ADMIN'
              AND wm.status = 'ACTIVE'
              AND wm.revoked_at IS NULL
        )
    );

CREATE POLICY client_brands_delete_policy ON public.client_brands
    FOR DELETE
    TO sylvar_app_user, authenticated
    USING (
        EXISTS (
            SELECT 1 FROM public.workspace_memberships wm
            WHERE wm.workspace_id = client_brands.workspace_id
              AND wm.user_id = public.current_app_user_id()
              AND wm.role = 'WORKSPACE_ADMIN'
              AND wm.status = 'ACTIVE'
              AND wm.revoked_at IS NULL
        )
    );

-- ---------------------------------------------------------------------
-- 6. Corrected agency_workspaces RLS Policies
-- ---------------------------------------------------------------------
ALTER TABLE public.agency_workspaces ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.agency_workspaces FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation_agency_workspaces ON public.agency_workspaces;
DROP POLICY IF EXISTS agency_workspaces_select_policy ON public.agency_workspaces;
DROP POLICY IF EXISTS agency_workspaces_insert_policy ON public.agency_workspaces;
DROP POLICY IF EXISTS agency_workspaces_update_policy ON public.agency_workspaces;
DROP POLICY IF EXISTS agency_workspaces_delete_policy ON public.agency_workspaces;

CREATE POLICY agency_workspaces_select_policy ON public.agency_workspaces
    FOR SELECT
    TO sylvar_app_user, authenticated
    USING (
        id = public.current_app_workspace_id()
        OR id IN (
            SELECT wm.workspace_id
            FROM public.workspace_memberships wm
            WHERE wm.user_id = public.current_app_user_id()
              AND wm.status = 'ACTIVE'
              AND wm.revoked_at IS NULL
        )
    );

CREATE POLICY agency_workspaces_insert_policy ON public.agency_workspaces
    FOR INSERT
    TO sylvar_app_user, authenticated
    WITH CHECK (
        public.current_app_user_id() IS NOT NULL
    );

CREATE POLICY agency_workspaces_update_policy ON public.agency_workspaces
    FOR UPDATE
    TO sylvar_app_user, authenticated
    USING (
        EXISTS (
            SELECT 1 FROM public.workspace_memberships wm
            WHERE wm.workspace_id = agency_workspaces.id
              AND wm.user_id = public.current_app_user_id()
              AND wm.role = 'WORKSPACE_ADMIN'
              AND wm.status = 'ACTIVE'
              AND wm.revoked_at IS NULL
        )
    )
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM public.workspace_memberships wm
            WHERE wm.workspace_id = agency_workspaces.id
              AND wm.user_id = public.current_app_user_id()
              AND wm.role = 'WORKSPACE_ADMIN'
              AND wm.status = 'ACTIVE'
              AND wm.revoked_at IS NULL
        )
    );

CREATE POLICY agency_workspaces_delete_policy ON public.agency_workspaces
    FOR DELETE
    TO sylvar_app_user, authenticated
    USING (
        EXISTS (
            SELECT 1 FROM public.workspace_memberships wm
            WHERE wm.workspace_id = agency_workspaces.id
              AND wm.user_id = public.current_app_user_id()
              AND wm.role = 'WORKSPACE_ADMIN'
              AND wm.status = 'ACTIVE'
              AND wm.revoked_at IS NULL
        )
    );
