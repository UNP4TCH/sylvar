# SYLVAR — Batch 3.1 Post-Migration Live Database Verification Report

**Date of Execution:** 2026-11-07  
**Database Host:** `aws-0-ap-southeast-2.pooler.supabase.com:5432`  
**Database Name:** `postgres`  
**Supabase Project Ref:** `apnqefdonksrxbqmnaou`  
**Runtime User:** `sylvar_app_user` (session_user: `sylvar_app_user`)  
**Scope:** Read-only schema verification and isolated transactional rollback behavioral testing of Migration 008 (`008_batch3_1_governance_hardening.sql`)

---

## Executive Summary

Migration 008 was manually applied via the Supabase SQL Editor and has been **fully verified on the live PostgreSQL database**.

Using the least-privileged runtime role (`sylvar_app_user`), all 9 verification items requested were inspected directly against PostgreSQL system catalogs (`pg_index`, `pg_constraint`, `pg_trigger`, `pg_proc`, `pg_roles`, `pg_class`, `pg_policies`). Furthermore, the functional behavior of the separation-of-duties trigger and governance constraints was directly tested using isolated test data inside a transaction that was explicitly rolled back, confirming end-to-end enforcement with **zero database mutation**.

**Overall Status: 100% PASS (All 9 items verified).**

---

## 1. Item-by-Item Verification Matrix

| # | Item to Verify | Verification Method | Live Catalog Evidence / Error Trapped | Status |
|---|---|---|---|:---:|
| 1 | `uq_approval_requests_pending_version` | Catalog query (`pg_index`, `pg_class`) + Live duplicate insertion test | Index valid (`indisvalid = true`), unique (`indisunique = true`). Duplicate PENDING insert blocked with `UniqueViolationError: duplicate key value violates unique constraint "uq_approval_requests_pending_version"`. | **PASS** |
| 2 | `uq_approval_requests_approved_version` | Catalog query (`pg_index`, `pg_class`) + Live duplicate insertion test | Index valid (`indisvalid = true`), unique (`indisunique = true`). Duplicate APPROVED insert blocked with `UniqueViolationError: duplicate key value violates unique constraint "uq_approval_requests_approved_version"`. | **PASS** |
| 3 | `uq_compliance_cert_version` | Catalog query (`pg_constraint`, `pg_index`) + Live duplicate cert test | Constraint valid (`convalidated = true`), index valid & unique. Second compliance certificate for same `asset_version_id` blocked with `UniqueViolationError: duplicate key value violates unique constraint "uq_compliance_cert_version"`. | **PASS** |
| 4 | `ck_approval_requests_decision_metadata` | Catalog query (`pg_constraint`) + Live invalid metadata insert test | CHECK constraint validated (`convalidated = true`). Attempt to insert PENDING with `decided_at IS NOT NULL` blocked with `CheckViolationError: new row for relation "approval_requests" violates check constraint "ck_approval_requests_decision_metadata"`. | **PASS** |
| 5 | `trg_approval_sod` | Catalog query (`pg_trigger`) | Trigger exists on `approval_requests`, timing `BEFORE UPDATE`, level `FOR EACH ROW`, status `tgenabled = 'O'` (Origin & Local, enabled). | **PASS** |
| 6 | Trigger function definition | Catalog query (`pg_proc`, `pg_get_functiondef`) | Function `trg_fn_enforce_approval_sod()` confirmed: immutability of decided requests, blocks submitter, blocks asset creator, blocks version creator, fails closed on missing ownership evidence. | **PASS** |
| 7 | Row-Level Security (RLS) on relevant tables | Catalog query (`pg_class.relrowsecurity`) | All 22 tables in public schema maintain `relrowsecurity = true`. Dedicated policies active on `approval_requests` and `compliance_certificates`. | **PASS** |
| 8 | Runtime role least-privilege privileges | Catalog query (`pg_roles`) | `sylvar_app_user` confirmed `rolsuper = false`, `rolbypassrls = false`, `rolcreaterole = false`, `rolcreatedb = false`. | **PASS** |
| 9 | Existing application operations working | Live SQL queries under `sylvar_app_user` | `SELECT count(*)` executed successfully across all public tables; index scans and query execution plans verified. | **PASS** |

---

## 2. Detailed Technical Evidence

### 2.1 Index Verification (`approval_requests` & `compliance_certificates`)

Queried from `pg_index` joined with `pg_class`:

```sql
-- uq_approval_requests_pending_version
CREATE UNIQUE INDEX uq_approval_requests_pending_version 
ON public.approval_requests USING btree (asset_version_id) 
WHERE ((status)::text = 'PENDING'::text);
-- Status: indisvalid=True, indisunique=True

-- uq_approval_requests_approved_version
CREATE UNIQUE INDEX uq_approval_requests_approved_version 
ON public.approval_requests USING btree (asset_version_id) 
WHERE ((status)::text = 'APPROVED'::text);
-- Status: indisvalid=True, indisunique=True

-- uq_compliance_cert_version
CREATE UNIQUE INDEX uq_compliance_cert_version 
ON public.compliance_certificates USING btree (asset_version_id);
-- Status: indisvalid=True, indisunique=True
```

Constraint entry in `pg_constraint`:
- `uq_compliance_cert_version`: `contype = 'u'` (UNIQUE), `convalidated = True`.

---

### 2.2 CHECK Constraint Verification

Queried from `pg_constraint`:
- **Constraint Name:** `ck_approval_requests_decision_metadata`
- **Table:** `approval_requests`
- **Validated:** `True`
- **Definition:**
  ```sql
  CHECK (
    (((status)::text = 'PENDING'::text) AND (decided_at IS NULL) AND (decided_by_user_id IS NULL))
    OR 
    (((status)::text = ANY (ARRAY['APPROVED'::varchar, 'REJECTED'::varchar, 'CHANGES_REQUESTED'::varchar]::text[])) 
     AND (decided_at IS NOT NULL) AND (decided_by_user_id IS NOT NULL))
  )
  ```

---

### 2.3 Trigger and Trigger Function Definition

Queried from `pg_trigger`:
- **Trigger:** `trg_approval_sod`
- **Enabled State:** `'O'` (`tgenabled = b'O'`, normal origin & local firing)
- **Definition:**
  ```sql
  CREATE TRIGGER trg_approval_sod 
  BEFORE UPDATE ON public.approval_requests 
  FOR EACH ROW 
  EXECUTE FUNCTION trg_fn_enforce_approval_sod()
  ```

Queried from `pg_proc` via `pg_get_functiondef`:
- **Function:** `public.trg_fn_enforce_approval_sod()`
- **Language:** `plpgsql`
- **Core Logic Verified:**
  1. **Terminal state immutability:**
     ```sql
     IF OLD.status IN ('APPROVED', 'REJECTED', 'CHANGES_REQUESTED') THEN
         RAISE EXCEPTION 'Cannot modify an already decided approval request'
             USING ERRCODE = '23514';
     END IF;
     ```
  2. **Submitter self-approval rejection:**
     ```sql
     IF NEW.decided_by_user_id IS NULL OR NEW.decided_by_user_id = OLD.submitted_by_user_id THEN
         RAISE EXCEPTION 'Separation of duties violation: submitter cannot approve'
             USING ERRCODE = '23514';
     END IF;
     ```
  3. **Asset creator approval rejection & fail-closed tenant validation:**
     ```sql
     SELECT created_by_user_id INTO v_asset_creator
     FROM content_assets
     WHERE id = OLD.asset_id
       AND workspace_id = OLD.workspace_id
       AND client_id = OLD.client_id;
     
     v_asset_found := FOUND;
     IF NOT v_asset_found OR v_asset_creator IS NULL THEN
         RAISE EXCEPTION 'Approval rejected: asset ownership evidence is missing'
             USING ERRCODE = '23514';
     END IF;
     
     IF NEW.decided_by_user_id = v_asset_creator THEN
         RAISE EXCEPTION 'Separation of duties violation: asset creator cannot approve'
             USING ERRCODE = '23514';
     END IF;
     ```
  4. **Version creator approval rejection & fail-closed version validation:**
     ```sql
     SELECT created_by_user_id INTO v_version_creator
     FROM asset_versions
     WHERE id = OLD.asset_version_id
       AND asset_id = OLD.asset_id;
     
     v_version_found := FOUND;
     IF NOT v_version_found OR v_version_creator IS NULL THEN
         RAISE EXCEPTION 'Approval rejected: version ownership evidence is missing'
             USING ERRCODE = '23514';
     END IF;
     
     IF NEW.decided_by_user_id = v_version_creator THEN
         RAISE EXCEPTION 'Separation of duties violation: version creator cannot approve'
             USING ERRCODE = '23514';
     END IF;
     ```

---

### 2.4 Least Privilege and RLS Verification

Queried from `pg_roles`:
- `rolname`: `sylvar_app_user`
- `rolsuper`: `False` (NOSUPERUSER)
- `rolbypassrls`: `False` (NOBYPASSRLS)
- `rolcreaterole`: `False` (NOCREATEROLE)
- `rolcreatedb`: `False` (NOCREATEDB)

Queried from `pg_class`:
- `agency_workspaces`: `relrowsecurity = True`
- `client_brands`: `relrowsecurity = True`
- `content_assets`: `relrowsecurity = True`
- `asset_versions`: `relrowsecurity = True`
- `audit_runs`: `relrowsecurity = True`
- `audit_checks`: `relrowsecurity = True`
- `approval_requests`: `relrowsecurity = True`
- `compliance_certificates`: `relrowsecurity = True`
- All other 14 tables in `public` schema have RLS enabled.

---

## 3. Transactional Rollback Behavioral Testing

To prove that the trigger and constraints are actively enforced (rather than merely defined), a dedicated test script (`test_live_trigger_and_constraints.py`) was executed against the live database under `sylvar_app_user`.

**Test Isolation Guarantee:**
- Executed inside a single PostgreSQL transaction (`BEGIN ... ROLLBACK`).
- Sub-cases executed within savepoints.
- Pre-test row counts: `approval_requests = 0`, `compliance_certificates = 0`.
- Post-test row counts: `approval_requests = 0`, `compliance_certificates = 0`.
- **Zero rows mutated or persisted.**

### Test Results

```
======================================================================
LIVE BEHAVIORAL VERIFICATION SUITE RESULTS
======================================================================
[TEST 1] Decision Metadata CHECK Constraint:
  Result: PASS
  Trapped Exception: CheckViolation: new row for relation "approval_requests" 
                     violates check constraint "ck_approval_requests_decision_metadata"

[TEST 2] Partial Unique Index (PENDING):
  Result: PASS
  Trapped Exception: UniqueViolation on uq_approval_requests_pending_version: 
                     duplicate key value violates unique constraint "uq_approval_requests_pending_version"

[TEST 3] Trigger Blocks Submitter Self-Approval:
  Result: PASS
  Trapped Exception: CheckViolation (ERRCODE 23514): 
                     Separation of duties violation: submitter cannot approve

[TEST 4] Trigger Blocks Content Asset Creator Approval:
  Result: PASS
  Trapped Exception: CheckViolation (ERRCODE 23514): 
                     Separation of duties violation: asset creator cannot approve

[TEST 5] Trigger Blocks Asset Version Creator Approval:
  Result: PASS
  Trapped Exception: CheckViolation (ERRCODE 23514): 
                     Separation of duties violation: version creator cannot approve

[TEST 6] Trigger Allows Independent Brand Manager Approval:
  Result: PASS
  Behavior: Successfully updated status to APPROVED with independent decided_by_user_id.

[TEST 7] Trigger Prevents Modification of Already-Decided Request:
  Result: PASS
  Trapped Exception: CheckViolation (ERRCODE 23514): 
                     Cannot modify an already decided approval request

[TEST 8] Partial Unique Index (APPROVED):
  Result: PASS
  Trapped Exception: UniqueViolation on uq_approval_requests_approved_version: 
                     duplicate key value violates unique constraint "uq_approval_requests_approved_version"

[TEST 9] Compliance Certificate Asset Version Uniqueness:
  Result: PASS
  Trapped Exception: UniqueViolation on uq_compliance_cert_version: 
                     duplicate key value violates unique constraint "uq_compliance_cert_version"

[MUTATION INTEGRITY AUDIT]
  Pre-test rows:  approval_requests=0, compliance_certificates=0
  Post-test rows: approval_requests=0, compliance_certificates=0
  Zero database mutation: CONFIRMED (100% clean rollback)
======================================================================
```

---

## 4. Application Query Compatibility

Under `sylvar_app_user`:
- Full read access verified across all 22 tables in `public`.
- Query execution plans on `approval_requests` and `compliance_certificates` confirmed using tenant isolation indices (`idx_approval_requests_client` and `idx_compliance_cert_lookup`).
- Local regression test suite remains at **38/38 PASS**.
- Frontend production build remains at **PASS** (96 modules, 0 errors).

---

## 5. Summary of Verification States

- **Checks Actually Verified on Live PostgreSQL:** 9 of 9 (100%)
- **Checks Blocked:** 0
- **Checks Not Run:** 0
- **Database Modality:** Read-only / Rollback-isolated testing
- **Production Records Affected:** 0

**Conclusion:** Migration 008 is verified, valid, active, and fully enforcing brand governance and separation-of-duties rules at the database engine level.

