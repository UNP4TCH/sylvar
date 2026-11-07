-- ==============================================================================
-- Migration 001: Identity, Workspaces & Client Brand Management
-- Phase 2 Baseline: Domains A & B
-- Enforces:
--  - Exactly three roles: WORKSPACE_ADMIN, BRAND_MANAGER, CONTENT_CREATOR
--  - Dual-tenant composite keys (workspace_id, client_id)
--  - RLS policies matching application session settings (app.current_workspace_id)
-- ==============================================================================

-- Enable UUID extension if not already present
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Enums
DO $$ BEGIN
    CREATE TYPE user_role AS ENUM ('WORKSPACE_ADMIN', 'BRAND_MANAGER', 'CONTENT_CREATOR');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE membership_status AS ENUM ('INVITED', 'ACTIVE', 'SUSPENDED', 'REVOKED');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE client_role AS ENUM ('BRAND_MANAGER', 'CONTENT_CREATOR');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE client_membership_status AS ENUM ('ACTIVE', 'REVOKED');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- 1. Users table (extends auth.users)
CREATE TABLE IF NOT EXISTS public.users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT NOT NULL UNIQUE,
    full_name TEXT,
    avatar_url TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

-- 2. Agency Workspaces table
CREATE TABLE IF NOT EXISTS public.agency_workspaces (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

CREATE INDEX IF NOT EXISTS idx_agency_workspaces_slug ON public.agency_workspaces(slug);

-- 3. Workspace Memberships table
CREATE TABLE IF NOT EXISTS public.workspace_memberships (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES public.agency_workspaces(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE ON UPDATE CASCADE,
    role public.user_role NOT NULL,
    status public.membership_status NOT NULL DEFAULT 'ACTIVE',
    revoked_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    CONSTRAINT uq_workspace_user UNIQUE (workspace_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_workspace_memberships_user ON public.workspace_memberships(user_id);
CREATE INDEX IF NOT EXISTS idx_workspace_memberships_lookup ON public.workspace_memberships(workspace_id, user_id, status);

-- 4. Client Brands table
CREATE TABLE IF NOT EXISTS public.client_brands (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES public.agency_workspaces(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    code TEXT NOT NULL,
    description TEXT,
    active_memory_version_id UUID NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    CONSTRAINT uq_client_brands_workspace_id UNIQUE (workspace_id, id),
    CONSTRAINT uq_client_brands_workspace_code UNIQUE (workspace_id, code)
);

CREATE INDEX IF NOT EXISTS idx_client_brands_workspace ON public.client_brands(workspace_id);

-- 5. Client Memberships table (Independent Client Assignment)
CREATE TABLE IF NOT EXISTS public.client_memberships (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    client_id UUID NOT NULL,
    user_id UUID NOT NULL,
    client_role public.client_role NOT NULL,
    status public.client_membership_status NOT NULL DEFAULT 'ACTIVE',
    revoked_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    CONSTRAINT uq_client_memberships_client_user UNIQUE (client_id, user_id),
    CONSTRAINT fk_client_brand_composite FOREIGN KEY (workspace_id, client_id)
        REFERENCES public.client_brands(workspace_id, id) ON DELETE CASCADE,
    CONSTRAINT fk_workspace_user_composite FOREIGN KEY (workspace_id, user_id)
        REFERENCES public.workspace_memberships(workspace_id, user_id) ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_client_memberships_lookup ON public.client_memberships(workspace_id, client_id, user_id, status);

-- Helper Context Functions (Resolves C-01 & C-02: Bridges custom backend JWT with PostgreSQL RLS)
CREATE OR REPLACE FUNCTION public.current_app_user_id() RETURNS UUID AS $$
BEGIN
    -- The API sets this transaction-local value only after verifying the
    -- Supabase JWT. The dedicated backend DB role does not rely on auth.uid().
    RETURN NULLIF(current_setting('app.current_user_id', true), '')::uuid;
END;
$$ LANGUAGE plpgsql STABLE;

CREATE OR REPLACE FUNCTION public.current_app_workspace_id() RETURNS UUID AS $$
BEGIN
    RETURN NULLIF(current_setting('app.current_workspace_id', true), '')::uuid;
END;
$$ LANGUAGE plpgsql STABLE;

CREATE OR REPLACE FUNCTION public.current_app_client_id() RETURNS UUID AS $$
BEGIN
    RETURN NULLIF(current_setting('app.current_client_id', true), '')::uuid;
END;
$$ LANGUAGE plpgsql STABLE;

-- Enable and Force RLS
ALTER TABLE public.agency_workspaces ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.agency_workspaces FORCE ROW LEVEL SECURITY;

ALTER TABLE public.workspace_memberships ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.workspace_memberships FORCE ROW LEVEL SECURITY;

ALTER TABLE public.client_brands ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.client_brands FORCE ROW LEVEL SECURITY;

ALTER TABLE public.client_memberships ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.client_memberships FORCE ROW LEVEL SECURITY;

-- Tenant Isolation Policies without circular bootstrap dependencies (Resolves C-01)
CREATE POLICY tenant_isolation_agency_workspaces ON public.agency_workspaces
    FOR ALL
    USING (
        id = public.current_app_workspace_id()
        OR id IN (
            SELECT wm.workspace_id FROM public.workspace_memberships wm
            WHERE wm.user_id = public.current_app_user_id() AND wm.status = 'ACTIVE'
        )
    );

CREATE POLICY tenant_isolation_workspace_memberships ON public.workspace_memberships
    FOR ALL
    USING (
        user_id = public.current_app_user_id()
        OR workspace_id = public.current_app_workspace_id()
    );

CREATE POLICY tenant_isolation_client_brands ON public.client_brands
    FOR ALL
    USING (
        (
            id IN (
                SELECT cm.client_id FROM public.client_memberships cm
                WHERE cm.user_id = public.current_app_user_id() AND cm.status = 'ACTIVE'
            )
        )
        OR (
            workspace_id = public.current_app_workspace_id()
            AND (
                (public.current_app_client_id() IS NOT NULL AND id = public.current_app_client_id())
                OR EXISTS (
                SELECT 1 FROM public.workspace_memberships wm
                WHERE wm.workspace_id = client_brands.workspace_id
                  AND wm.user_id = public.current_app_user_id()
                  AND wm.status = 'ACTIVE'
                  AND wm.revoked_at IS NULL
                  AND wm.role = 'WORKSPACE_ADMIN'
                )
            )
        )
    )
    WITH CHECK (
        workspace_id = public.current_app_workspace_id()
        AND EXISTS (
            SELECT 1 FROM public.workspace_memberships wm
            WHERE wm.workspace_id = client_brands.workspace_id
              AND wm.user_id = public.current_app_user_id()
              AND wm.status = 'ACTIVE'
              AND wm.revoked_at IS NULL
              AND wm.role = 'WORKSPACE_ADMIN'
        )
    );

CREATE POLICY tenant_isolation_client_memberships ON public.client_memberships
    FOR ALL
    USING (
        user_id = public.current_app_user_id()
        OR (
            workspace_id = public.current_app_workspace_id()
            AND (
                public.current_app_client_id() IS NULL
                OR client_id = public.current_app_client_id()
            )
        )
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
