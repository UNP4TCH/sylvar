-- ==============================================================================
-- Migration 002: Document Ingestion, Candidate Rules & Living Brand Memory
-- Phase 3 Baseline: Domains C & D
-- Enforces:
--  - Multi-tenant composite keys (workspace_id, client_id)
--  - Canonical document statuses (PENDING, PARSING, EXTRACTED, REPLACED, FAILED)
--  - Rule categories (TERMINOLOGY, FACT, COLOR, VOICE)
--  - Candidate review states (PENDING_REVIEW, APPROVED, MODIFIED_APPROVED, REJECTED)
--  - Immutable rule revisions and pinned memory snapshots with SHA-256 hashes
-- ==============================================================================

DO $$ BEGIN
    CREATE TYPE document_status AS ENUM ('PENDING', 'PARSING', 'EXTRACTED', 'REPLACED', 'FAILED');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE rule_category AS ENUM ('TERMINOLOGY', 'FACT', 'COLOR', 'VOICE');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE candidate_status AS ENUM ('PENDING_REVIEW', 'APPROVED', 'MODIFIED_APPROVED', 'REJECTED');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE memory_version_status AS ENUM ('DRAFT', 'ACTIVE', 'SUPERSEDED', 'ARCHIVED');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- 6. Guideline Documents table
CREATE TABLE IF NOT EXISTS public.guideline_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    client_id UUID NOT NULL,
    title TEXT NOT NULL,
    filename TEXT NOT NULL,
    file_format TEXT NOT NULL,
    file_size_bytes BIGINT NOT NULL,
    sha256_hash TEXT NOT NULL,
    processing_status public.document_status NOT NULL DEFAULT 'PENDING',
    error_details TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    CONSTRAINT fk_guideline_docs_client FOREIGN KEY (workspace_id, client_id)
        REFERENCES public.client_brands(workspace_id, id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_guideline_docs_lookup ON public.guideline_documents(workspace_id, client_id);

-- 7. Document Sections table
CREATE TABLE IF NOT EXISTS public.document_sections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    client_id UUID NOT NULL,
    document_id UUID NOT NULL REFERENCES public.guideline_documents(id) ON DELETE CASCADE,
    section_number INT NOT NULL,
    heading TEXT NULL,
    content TEXT NOT NULL,
    page_number INT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    CONSTRAINT fk_document_sections_client FOREIGN KEY (workspace_id, client_id)
        REFERENCES public.client_brands(workspace_id, id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_document_sections_lookup ON public.document_sections(workspace_id, client_id, document_id);

-- 8. Extracted Candidates table
CREATE TABLE IF NOT EXISTS public.extracted_candidates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    client_id UUID NOT NULL,
    document_id UUID NOT NULL REFERENCES public.guideline_documents(id) ON DELETE CASCADE,
    category public.rule_category NOT NULL,
    payload JSONB NOT NULL,
    review_status public.candidate_status NOT NULL DEFAULT 'PENDING_REVIEW',
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    CONSTRAINT fk_extracted_candidates_client FOREIGN KEY (workspace_id, client_id)
        REFERENCES public.client_brands(workspace_id, id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_extracted_candidates_lookup ON public.extracted_candidates(workspace_id, client_id, review_status);

-- 9. Brand Memory Versions table
CREATE TABLE IF NOT EXISTS public.brand_memory_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    client_id UUID NOT NULL,
    version_number INT NOT NULL,
    version_tag TEXT NOT NULL,
    status public.memory_version_status NOT NULL DEFAULT 'DRAFT',
    change_summary TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    CONSTRAINT uq_memory_versions_tag UNIQUE (workspace_id, client_id, version_tag),
    CONSTRAINT fk_brand_memory_versions_client FOREIGN KEY (workspace_id, client_id)
        REFERENCES public.client_brands(workspace_id, id) ON DELETE CASCADE
);

-- 10. Brand Rules table
CREATE TABLE IF NOT EXISTS public.brand_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    client_id UUID NOT NULL,
    rule_code TEXT NOT NULL,
    category public.rule_category NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    CONSTRAINT uq_brand_rules_code UNIQUE (workspace_id, client_id, rule_code),
    CONSTRAINT fk_brand_rules_client FOREIGN KEY (workspace_id, client_id)
        REFERENCES public.client_brands(workspace_id, id) ON DELETE CASCADE
);

-- 11. Brand Rule Revisions table (Immutable)
CREATE TABLE IF NOT EXISTS public.brand_rule_revisions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_id UUID NOT NULL REFERENCES public.brand_rules(id) ON DELETE CASCADE,
    revision_number INT NOT NULL,
    content JSONB NOT NULL,
    rationale TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    CONSTRAINT uq_rule_revision UNIQUE (rule_id, revision_number)
);

-- 12. Brand Memory Version Rules (Association)
CREATE TABLE IF NOT EXISTS public.brand_memory_version_rules (
    memory_version_id UUID NOT NULL REFERENCES public.brand_memory_versions(id) ON DELETE CASCADE,
    rule_revision_id UUID NOT NULL REFERENCES public.brand_rule_revisions(id) ON DELETE CASCADE,
    PRIMARY KEY (memory_version_id, rule_revision_id)
);

-- 13. Brand Memory Snapshots table (Materialized JSONB with SHA-256 Hash)
CREATE TABLE IF NOT EXISTS public.brand_memory_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    client_id UUID NOT NULL,
    memory_version_id UUID NOT NULL REFERENCES public.brand_memory_versions(id) ON DELETE CASCADE,
    snapshot_hash TEXT NOT NULL UNIQUE,
    snapshot_data JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    CONSTRAINT fk_memory_snapshots_client FOREIGN KEY (workspace_id, client_id)
        REFERENCES public.client_brands(workspace_id, id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_brand_memory_snapshots_hash ON public.brand_memory_snapshots(snapshot_hash);

-- Enable & Force RLS (including brand_rule_revisions and brand_memory_version_rules)
ALTER TABLE public.guideline_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.guideline_documents FORCE ROW LEVEL SECURITY;

ALTER TABLE public.document_sections ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.document_sections FORCE ROW LEVEL SECURITY;

ALTER TABLE public.extracted_candidates ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.extracted_candidates FORCE ROW LEVEL SECURITY;

ALTER TABLE public.brand_memory_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.brand_memory_versions FORCE ROW LEVEL SECURITY;

ALTER TABLE public.brand_rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.brand_rules FORCE ROW LEVEL SECURITY;

ALTER TABLE public.brand_rule_revisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.brand_rule_revisions FORCE ROW LEVEL SECURITY;

ALTER TABLE public.brand_memory_version_rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.brand_memory_version_rules FORCE ROW LEVEL SECURITY;

ALTER TABLE public.brand_memory_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.brand_memory_snapshots FORCE ROW LEVEL SECURITY;

-- Tenant Isolation Policies using public.current_app_workspace_id() & public.current_app_client_id()
CREATE POLICY tenant_isolation_guideline_documents ON public.guideline_documents
    FOR ALL
    USING (
        workspace_id = public.current_app_workspace_id()
        AND client_id = public.current_app_client_id()
    );

CREATE POLICY tenant_isolation_document_sections ON public.document_sections
    FOR ALL
    USING (
        workspace_id = public.current_app_workspace_id()
        AND client_id = public.current_app_client_id()
    );

CREATE POLICY tenant_isolation_extracted_candidates ON public.extracted_candidates
    FOR ALL
    USING (
        workspace_id = public.current_app_workspace_id()
        AND client_id = public.current_app_client_id()
    );

CREATE POLICY tenant_isolation_brand_memory_versions ON public.brand_memory_versions
    FOR ALL
    USING (
        workspace_id = public.current_app_workspace_id()
        AND client_id = public.current_app_client_id()
    );

CREATE POLICY tenant_isolation_brand_rules ON public.brand_rules
    FOR ALL
    USING (
        workspace_id = public.current_app_workspace_id()
        AND client_id = public.current_app_client_id()
    );

-- Missing RLS Coverage resolved: rule revisions scoped to client's brand rules
CREATE POLICY tenant_isolation_brand_rule_revisions ON public.brand_rule_revisions
    FOR ALL
    USING (
        rule_id IN (
            SELECT r.id FROM public.brand_rules r
            WHERE r.workspace_id = public.current_app_workspace_id()
              AND r.client_id = public.current_app_client_id()
        )
    );

-- Missing RLS Coverage resolved: version rules scoped to client's memory versions
CREATE POLICY tenant_isolation_brand_memory_version_rules ON public.brand_memory_version_rules
    FOR ALL
    USING (
        memory_version_id IN (
            SELECT v.id FROM public.brand_memory_versions v
            WHERE v.workspace_id = public.current_app_workspace_id()
              AND v.client_id = public.current_app_client_id()
        )
    );

CREATE POLICY tenant_isolation_brand_memory_snapshots ON public.brand_memory_snapshots
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
