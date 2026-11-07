-- =====================================================================
-- SYLVAR — Migration 007: Batch 2A Final Security Correction
-- =====================================================================
-- STATUS: PREPARED / PENDING APPROVAL — DO NOT APPLY TO LIVE DATABASE
--
-- Security Objectives:
-- 1. Strictly harden the SECURITY DEFINER function ACL:
--    - Revoke EXECUTE from service_role, anon, authenticated, and PUBLIC.
--    - Grant EXECUTE exclusively to sylvar_app_user (trusted FastAPI runtime).
--    - Preserve postgres ownership, prosecdef, and safe search_path.
-- 2. Reject deliberately revoked memberships:
--    - If a user was previously revoked (status = 'REVOKED' or revoked_at IS NOT NULL),
--      invitation acceptance is rejected with SQLSTATE 42501.
--    - An existing active WORKSPACE_ADMIN cannot be downgraded.
--    - Existing active roles are not overwritten.
--    - Fresh invitees receive strictly the invited role.
-- 3. Strip any residual default privileges from 'anon' on workspace_invitations.
-- =====================================================================

-- 1. Preconditions Verification
DO $$
BEGIN
    -- Ensure Migration 006 table exists
    IF NOT EXISTS (
        SELECT 1 FROM pg_tables 
        WHERE schemaname = 'public' AND tablename = 'workspace_invitations'
    ) THEN
        RAISE EXCEPTION 'Precondition failed: table public.workspace_invitations does not exist. Migration 006 must be applied first.'
            USING ERRCODE = 'P0002';
    END IF;

    -- Ensure accept_workspace_invitation function exists
    IF NOT EXISTS (
        SELECT 1 FROM pg_proc p
        JOIN pg_namespace n ON p.pronamespace = n.oid
        WHERE n.nspname = 'public' AND p.proname = 'accept_workspace_invitation'
    ) THEN
        RAISE EXCEPTION 'Precondition failed: function public.accept_workspace_invitation does not exist. Migration 006 must be applied first.'
            USING ERRCODE = 'P0002';
    END IF;

    -- Ensure sylvar_app_user role exists
    IF NOT EXISTS (
        SELECT 1 FROM pg_roles WHERE rolname = 'sylvar_app_user'
    ) THEN
        RAISE EXCEPTION 'Precondition failed: role sylvar_app_user does not exist.'
            USING ERRCODE = 'P0002';
    END IF;
END;
$$;

-- 2. Idempotent Function Definition with Explicit Revocation Guard
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

    -- 2. Lookup caller's verified profile from public.users (explicitly schema-qualified)
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

-- 3. Set Function Owner
ALTER FUNCTION public.accept_workspace_invitation(UUID, UUID) OWNER TO postgres;

-- 4. Enforce Least-Privilege Function ACL
-- Revoke all execute privileges from PUBLIC, authenticated, anon, and service_role
REVOKE ALL ON FUNCTION public.accept_workspace_invitation(UUID, UUID) FROM PUBLIC, authenticated, anon, service_role;

-- Grant EXECUTE exclusively to sylvar_app_user
GRANT EXECUTE ON FUNCTION public.accept_workspace_invitation(UUID, UUID) TO sylvar_app_user;

-- 5. Strip Default Privileges from anon on workspace_invitations
REVOKE ALL ON public.workspace_invitations FROM anon;

