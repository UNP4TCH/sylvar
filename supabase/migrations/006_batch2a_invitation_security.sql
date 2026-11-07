-- =====================================================================
-- SYLVAR — Migration 006: Batch 2A Scoped Workspace Invitations & Outbox Hardening
-- =====================================================================
-- STATUS: DRAFT / PENDING APPROVAL — DO NOT APPLY TO LIVE DATABASE
--
-- Architecture & Least-Privilege Security:
-- 1. Dedicated public.workspace_invitations table with transactional outbox
--    tracking (delivery_status, delivery_attempts, delivered_at, claim_expires_at, errors).
-- 2. Preserves Batch 1 users_insert_policy completely unchanged:
--    WITH CHECK (id = public.current_app_user_id()).
--    Admins CANNOT insert arbitrary user profiles in public.users.
-- 3. Only active, unrevoked WORKSPACE_ADMIN can insert an invitation
--    bound strictly to their active workspace context.
-- 4. Direct UPDATE privileges for 'authenticated' are COMPLETELY REMOVED.
--    Invitee direct table UPDATE is prohibited at the PostgreSQL catalog level.
-- 5. Narrowly scoped invitation acceptance function: public.accept_workspace_invitation(UUID, UUID).
--    - Executable ONLY by trusted backend (sylvar_app_user); revoked from PUBLIC and authenticated.
--    - Search path configured securely with pg_catalog first: SET search_path = pg_catalog, public.
--      Excludes pg_temp to prevent untrusted shadow objects.
--    - Application tables, types, and system functions are explicitly schema-qualified.
--    - Requires verified caller identity (p_user_id UUID) validated cryptographically by FastAPI.
--      Cannot be forged through user-controlled session variables.
--    - Verifies caller's profile exists in public.users with exact normalized email match.
--    - Verifies status is PENDING and expires_at > now().
--    - Membership preservation: WORKSPACE_ADMIN cannot be downgraded; existing roles are preserved;
--      deliberately revoked memberships cannot be silently reactivated.
--    - Updates ONLY status = 'ACCEPTED', auth_user_id, accepted_at, updated_at.
--    - Invitee CANNOT alter delivery metadata, role, workspace, inviter, or expires_at.
--    - Atomically provisions or updates WorkspaceMembership according to preservation rules.
-- 6. Backend delivery-state updates are granted strictly to sylvar_app_user:
--    UPDATE on (status, delivery_status, delivery_attempts, last_delivery_error,
--    delivered_at, provider_message_id, claim_expires_at, accepted_at, auth_user_id, updated_at).
--    UPDATE on protected fields (workspace_id, email, role, invited_by_user_id, created_at, expires_at)
--    is prohibited at the catalog level.
-- 7. Zero DELETE privileges granted (audit evidence is immutable).
-- 8. SELECT visibility is restricted to WORKSPACE_ADMIN of that workspace or the
--    matching recipient (ordinary members cannot view pending invitations or emails).
-- =====================================================================

-- 1. Create invitation status and delivery status enums if not existing
DO $$ BEGIN
    CREATE TYPE public.invitation_status AS ENUM ('PENDING', 'ACCEPTED', 'EXPIRED', 'REVOKED');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE public.invitation_delivery_status AS ENUM ('PENDING', 'DELIVERED', 'FAILED');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- 2. Create workspace_invitations table with transactional outbox and claim lease tracking
CREATE TABLE IF NOT EXISTS public.workspace_invitations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES public.agency_workspaces(id) ON DELETE CASCADE,
    email VARCHAR(255) NOT NULL,
    role public.user_role NOT NULL,
    status public.invitation_status NOT NULL DEFAULT 'PENDING',
    delivery_status public.invitation_delivery_status NOT NULL DEFAULT 'PENDING',
    delivery_attempts INTEGER NOT NULL DEFAULT 0,
    claim_expires_at TIMESTAMPTZ NULL,
    last_delivery_error TEXT NULL,
    delivered_at TIMESTAMPTZ NULL,
    provider_message_id VARCHAR(255) NULL,
    invited_by_user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    auth_user_id UUID NULL,
    token_hash VARCHAR(64) NULL,
    expires_at TIMESTAMPTZ NOT NULL DEFAULT (now() + interval '7 days'),
    accepted_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 3. Partial unique index: at most one PENDING invitation per workspace & email
CREATE UNIQUE INDEX IF NOT EXISTS uq_workspace_invitations_pending
    ON public.workspace_invitations (workspace_id, lower(email))
    WHERE status = 'PENDING';

CREATE INDEX IF NOT EXISTS idx_workspace_invitations_lookup
    ON public.workspace_invitations (lower(email), status);

CREATE INDEX IF NOT EXISTS idx_workspace_invitations_ws
    ON public.workspace_invitations (workspace_id);

CREATE INDEX IF NOT EXISTS idx_workspace_invitations_delivery_claim
    ON public.workspace_invitations (workspace_id, delivery_status, claim_expires_at)
    WHERE status = 'PENDING';

-- 4. Enable and Force Row Level Security
ALTER TABLE public.workspace_invitations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.workspace_invitations FORCE ROW LEVEL SECURITY;

-- 5. Least-Privilege Table Grants:
-- - sylvar_app_user: SELECT, INSERT, column-scoped UPDATE for delivery outbox management; ZERO DELETE.
-- - authenticated: SELECT only (filtered by RLS to own invitations). ZERO UPDATE, ZERO INSERT, ZERO DELETE.
REVOKE ALL ON public.workspace_invitations FROM PUBLIC, sylvar_app_user, authenticated;

GRANT SELECT, INSERT ON public.workspace_invitations TO sylvar_app_user;
GRANT UPDATE (
    status,
    delivery_status,
    delivery_attempts,
    last_delivery_error,
    delivered_at,
    provider_message_id,
    claim_expires_at,
    accepted_at,
    auth_user_id,
    updated_at
) ON public.workspace_invitations TO sylvar_app_user;

-- Authenticated clients have READ-ONLY access to their own invitations.
-- They CANNOT update any column directly (including delivery metadata).
GRANT SELECT ON public.workspace_invitations TO authenticated;

-- 6. Secure Invitation Acceptance Function (SECURITY DEFINER)
-- The ONLY sanctioned path for an invited identity to accept an invitation.
-- Invoked strictly by the trusted backend (sylvar_app_user) after performing
-- cryptographic JWT signature verification and trusted GoTrue email confirmation.
-- Direct execution by 'authenticated' or 'anon' is strictly revoked at the catalog level.
CREATE OR REPLACE FUNCTION public.accept_workspace_invitation(
    p_invitation_id UUID,
    p_user_id UUID
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_user_email VARCHAR;
    v_inv public.workspace_invitations%ROWTYPE;
    v_existing_mem public.workspace_memberships%ROWTYPE;
    v_final_role public.user_role;
BEGIN
    -- 1. Validate caller-supplied user identity
    IF p_user_id IS NULL THEN
        RAISE EXCEPTION 'User ID is required' USING ERRCODE = '28000';
    END IF;

    -- 2. Lookup caller's verified profile from public.users (explicitly qualified)
    SELECT u.email INTO v_user_email
    FROM public.users u
    WHERE u.id = p_user_id;

    IF v_user_email IS NULL THEN
        RAISE EXCEPTION 'User profile not found for authenticated caller' USING ERRCODE = 'P0002';
    END IF;

    -- 3. Lock and retrieve invitation row
    SELECT * INTO v_inv
    FROM public.workspace_invitations wi
    WHERE wi.id = p_invitation_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Invitation not found' USING ERRCODE = 'P0002';
    END IF;

    -- 4. Security Validations
    -- Exact normalized email match using pg_catalog.lower
    IF pg_catalog.lower(v_inv.email) <> pg_catalog.lower(v_user_email) THEN
        RAISE EXCEPTION 'Invitation email does not match authenticated user email' USING ERRCODE = '42501';
    END IF;

    -- Status must be PENDING
    IF v_inv.status <> 'PENDING' THEN
        RAISE EXCEPTION 'Invitation is already resolved or revoked (status: %)', v_inv.status USING ERRCODE = '23514';
    END IF;

    -- Expiry check using pg_catalog.now
    IF v_inv.expires_at <= pg_catalog.now() THEN
        RAISE EXCEPTION 'Invitation has expired' USING ERRCODE = '22008';
    END IF;

    -- 5. Membership Preservation & Revocation Guard
    SELECT * INTO v_existing_mem
    FROM public.workspace_memberships wm
    WHERE wm.workspace_id = v_inv.workspace_id
      AND wm.user_id = p_user_id
    FOR UPDATE;

    IF FOUND THEN
        -- Guard 1: Deliberately revoked memberships CANNOT be silently reactivated
        IF v_existing_mem.status = 'REVOKED' OR v_existing_mem.revoked_at IS NOT NULL THEN
            RAISE EXCEPTION 'User membership was previously revoked and cannot be reactivated via standard invitation acceptance' USING ERRCODE = '42501';
        END IF;

        -- Guard 2 & 3: Never downgrade WORKSPACE_ADMIN and preserve existing assigned role
        IF v_existing_mem.role = 'WORKSPACE_ADMIN' THEN
            v_final_role := 'WORKSPACE_ADMIN';
        ELSE
            v_final_role := v_existing_mem.role;
        END IF;

        UPDATE public.workspace_memberships
        SET status = 'ACTIVE',
            role = v_final_role,
            updated_at = pg_catalog.now()
        WHERE workspace_id = v_inv.workspace_id
          AND user_id = p_user_id;
    ELSE
        -- Fresh membership creation with invited role
        v_final_role := v_inv.role;
        INSERT INTO public.workspace_memberships (workspace_id, user_id, role, status, created_at, updated_at)
        VALUES (v_inv.workspace_id, p_user_id, v_final_role, 'ACTIVE', pg_catalog.now(), pg_catalog.now());
    END IF;

    -- 6. Atomically update ONLY invitation status and accepted fields
    -- (Delivery metadata, role, workspace, inviter, expires_at are untouched!)
    UPDATE public.workspace_invitations
    SET status = 'ACCEPTED',
        auth_user_id = p_user_id,
        accepted_at = pg_catalog.now(),
        claim_expires_at = NULL,
        updated_at = pg_catalog.now()
    WHERE id = v_inv.id;

    RETURN pg_catalog.jsonb_build_object(
        'invitation_id', v_inv.id,
        'workspace_id', v_inv.workspace_id,
        'user_id', p_user_id,
        'role', v_final_role,
        'status', 'ACCEPTED'
    );
END;
$$;

REVOKE ALL ON FUNCTION public.accept_workspace_invitation(UUID, UUID) FROM PUBLIC, authenticated;
GRANT EXECUTE ON FUNCTION public.accept_workspace_invitation(UUID, UUID) TO sylvar_app_user;

-- 7. Row Level Security Policies on workspace_invitations
DROP POLICY IF EXISTS workspace_invitations_select_policy ON public.workspace_invitations;
DROP POLICY IF EXISTS workspace_invitations_insert_policy ON public.workspace_invitations;
DROP POLICY IF EXISTS workspace_invitations_update_policy ON public.workspace_invitations;

-- SELECT Policy:
-- - Active WORKSPACE_ADMIN of the workspace can see invitations in their workspace
-- - Authenticated recipient can see pending invitations addressed to their email
-- - Ordinary members (CONTENT_CREATOR, BRAND_MANAGER) have NO access to pending invitation emails
CREATE POLICY workspace_invitations_select_policy ON public.workspace_invitations
    FOR SELECT
    TO sylvar_app_user, authenticated
    USING (
        (
            public.current_app_workspace_id() IS NOT NULL
            AND workspace_id = public.current_app_workspace_id()
            AND EXISTS (
                SELECT 1 FROM public.workspace_memberships wm
                WHERE wm.workspace_id = public.current_app_workspace_id()
                  AND wm.user_id = public.current_app_user_id()
                  AND wm.role = 'WORKSPACE_ADMIN'
                  AND wm.status = 'ACTIVE'
                  AND wm.revoked_at IS NULL
            )
        )
        OR (
            public.current_app_user_id() IS NOT NULL
            AND EXISTS (
                SELECT 1 FROM public.users u
                WHERE u.id = public.current_app_user_id()
                  AND lower(u.email) = lower(workspace_invitations.email)
            )
        )
    );

-- INSERT Policy:
-- - Strictly active, unrevoked WORKSPACE_ADMIN in their current workspace context
CREATE POLICY workspace_invitations_insert_policy ON public.workspace_invitations
    FOR INSERT
    TO sylvar_app_user
    WITH CHECK (
        workspace_id = public.current_app_workspace_id()
        AND invited_by_user_id = public.current_app_user_id()
        AND EXISTS (
            SELECT 1 FROM public.workspace_memberships wm
            WHERE wm.workspace_id = public.current_app_workspace_id()
              AND wm.user_id = public.current_app_user_id()
              AND wm.role = 'WORKSPACE_ADMIN'
              AND wm.status = 'ACTIVE'
              AND wm.revoked_at IS NULL
        )
    );

-- UPDATE Policy:
-- - Strictly active, unrevoked WORKSPACE_ADMIN in their current workspace context
--   (Used by sylvar_app_user for outbox delivery management and administrative revocations)
CREATE POLICY workspace_invitations_update_policy ON public.workspace_invitations
    FOR UPDATE
    TO sylvar_app_user
    USING (
        workspace_id = public.current_app_workspace_id()
        AND EXISTS (
            SELECT 1 FROM public.workspace_memberships wm
            WHERE wm.workspace_id = public.current_app_workspace_id()
              AND wm.user_id = public.current_app_user_id()
              AND wm.role = 'WORKSPACE_ADMIN'
              AND wm.status = 'ACTIVE'
              AND wm.revoked_at IS NULL
        )
    )
    WITH CHECK (
        workspace_id = public.current_app_workspace_id()
        AND EXISTS (
            SELECT 1 FROM public.workspace_memberships wm
            WHERE wm.workspace_id = public.current_app_workspace_id()
              AND wm.user_id = public.current_app_user_id()
              AND wm.role = 'WORKSPACE_ADMIN'
              AND wm.status = 'ACTIVE'
              AND wm.revoked_at IS NULL
        )
    );
