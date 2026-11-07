-- ============================================================================
-- SYLVAR Database Migration: 008_batch3_1_governance_hardening.sql
-- Batch 3.1: Governance Hardening & Integration Verification
-- Partial unique indexes, separation of duties trigger, decision constraints
-- ============================================================================

-- 1. PARTIAL UNIQUE INDEXES: APPROVAL REQUESTS
-- Exactly one PENDING approval request per asset_version
CREATE UNIQUE INDEX IF NOT EXISTS uq_approval_requests_pending_version
    ON approval_requests (asset_version_id)
    WHERE status = 'PENDING';

-- Exactly one APPROVED approval request per asset_version
CREATE UNIQUE INDEX IF NOT EXISTS uq_approval_requests_approved_version
    ON approval_requests (asset_version_id)
    WHERE status = 'APPROVED';

-- 2. COMPLIANCE CERTIFICATES: UNIQUE ASSET VERSION
-- Exactly one compliance certificate may exist per asset_version
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_compliance_cert_version'
    ) THEN
        ALTER TABLE compliance_certificates
            ADD CONSTRAINT uq_compliance_cert_version UNIQUE (asset_version_id);
    END IF;
END $$;

-- 3. CHECK CONSTRAINT: DECISION METADATA INTEGRITY
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'ck_approval_requests_decision_metadata'
    ) THEN
        ALTER TABLE approval_requests
            ADD CONSTRAINT ck_approval_requests_decision_metadata
            CHECK (
                (status = 'PENDING' AND decided_at IS NULL AND decided_by_user_id IS NULL)
                OR
                (status IN ('APPROVED', 'REJECTED', 'CHANGES_REQUESTED') AND decided_at IS NOT NULL AND decided_by_user_id IS NOT NULL)
            );
    END IF;
END $$;

-- 4. TRIGGER: SEPARATION OF DUTIES & TERMINAL STATE IMMUTABILITY
CREATE OR REPLACE FUNCTION trg_fn_enforce_approval_sod()
RETURNS TRIGGER AS $$
DECLARE
    v_asset_creator UUID;
    v_version_creator UUID;
BEGIN
    -- 1. Immutability of decided requests
    IF OLD.status IN ('APPROVED', 'REJECTED', 'CHANGES_REQUESTED') THEN
        RAISE EXCEPTION 'Cannot modify an already decided approval request (status: %)', OLD.status
            USING ERRCODE = '23514';
    END IF;

    -- 2. If transitioning to APPROVED, enforce separation of duties
    IF NEW.status = 'APPROVED' THEN
        -- Submitter check
        IF NEW.decided_by_user_id = OLD.submitted_by_user_id THEN
            RAISE EXCEPTION 'Separation of duties violation: submitter cannot approve submission'
                USING ERRCODE = '23514';
        END IF;

        -- Asset creator check
        SELECT created_by_user_id INTO v_asset_creator
        FROM content_assets
        WHERE id = OLD.asset_id;

        IF v_asset_creator IS NOT NULL AND NEW.decided_by_user_id = v_asset_creator THEN
            RAISE EXCEPTION 'Separation of duties violation: asset creator cannot approve submission'
                USING ERRCODE = '23514';
        END IF;

        -- Version creator check
        SELECT created_by_user_id INTO v_version_creator
        FROM asset_versions
        WHERE id = OLD.asset_version_id;

        IF v_version_creator IS NOT NULL AND NEW.decided_by_user_id = v_version_creator THEN
            RAISE EXCEPTION 'Separation of duties violation: version creator cannot approve submission'
                USING ERRCODE = '23514';
        END IF;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_approval_sod ON approval_requests;
CREATE TRIGGER trg_approval_sod
    BEFORE UPDATE ON approval_requests
    FOR EACH ROW
    EXECUTE FUNCTION trg_fn_enforce_approval_sod();

-- 5. GRANTS TO sylvar_app_user
GRANT SELECT, INSERT, UPDATE, DELETE ON approval_requests TO sylvar_app_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON compliance_certificates TO sylvar_app_user;
GRANT EXECUTE ON FUNCTION trg_fn_enforce_approval_sod() TO sylvar_app_user;

